import asyncio
from dataclasses import dataclass
import os
import shlex
import time
from python.helpers import async_subprocess
from python.helpers.tool import Tool, Response
from python.helpers import files, rfc_exchange
from python.helpers.print_style import PrintStyle
from python.helpers.shell_local import LocalInteractiveSession
from python.helpers.shell_ssh import SSHInteractiveSession
from python.helpers.docker import DockerContainerManager
from python.helpers.messages import truncate_text
import re

@dataclass
class State:
    shells: dict[int, LocalInteractiveSession | SSHInteractiveSession]
    docker: DockerContainerManager | None

class CodeExecution(Tool):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ssh_key = kwargs.get('ssh_key', '~/.ssh/id_rsa')
        self.root_password = None
        self.state_prepared = False
        self.state = None

    async def execute(self, **kwargs):
        await self.agent.handle_intervention()
        await self.prepare_state()
        runtime = self.args.get("runtime", "").lower().strip()
        session = int(self.args.get("session", 0))
        if runtime == "python":
            response = await self.execute_python_code(
                code=self.args["code"], session=session
            )
        elif runtime == "nodejs":
            response = await self.execute_nodejs_code(
                code=self.args["code"], session=session
            )
        elif runtime == "terminal":
            response = await self.execute_terminal_command(
                command=self.args["code"], session=session
            )
        elif runtime == "output":
            response = await self.get_terminal_output(
                session=session, first_output_timeout=60, between_output_timeout=5
            )
        elif runtime == "reset":
            response = await self.reset_terminal(session=session)
        else:
            response = self.agent.read_prompt(
                "fw.code.runtime_wrong.md", runtime=runtime
            )
        if not response:
            response = self.agent.read_prompt(
                "fw.code.info.md", info=self.agent.read_prompt("fw.code.no_output.md")
            )
        return Response(message=response, break_loop=False)

    def get_log_object(self):
        return self.agent.context.log.log(
            type="code_exe",
            heading=f"{self.agent.agent_name}: Using tool '{self.name}'",
            content="",
            kvps=self.args,
        )

    async def after_execution(self, response, **kwargs):
        self.agent.hist_add_tool_result(self.name, response.message)

    # In /Users/ashwath/Desktop/Sample App/agent_zero/python/tools/code_execution_tool.py
    async def prepare_state(self, reset=False, session=None):
        if not self.state_prepared:
            self.state_prepared = True
            if os.path.exists(self.ssh_key):
                await async_subprocess(f"chmod 600 {self.ssh_key}")
            self.root_password = os.getenv("RFC_PASSWORD", "rfc123")
            self.state = self.agent.get_data("_cet_state")
            if not self.state or reset:
                docker = None
                shells = {} if not self.state else self.state.shells.copy()
                if session is not None and session in shells:
                    shells[session].close()
                    del shells[session]
                elif reset and not session:
                    for s in list(shells.keys()):
                        shells[s].close()
                shells = {}
                if 0 not in shells:
                    shell = LocalInteractiveSession()
                    shells[0] = shell
                    await shell.connect()
                self.state = State(shells=shells, docker=docker)
            self.agent.set_data("_cet_state", self.state)

    async def execute_python_code(self, session: int, code: str, reset: bool = False):
        escaped_code = shlex.quote(code)
        command = f"ipython -c {escaped_code}"
        return await self.terminal_session(session, command, reset)

    async def execute_nodejs_code(self, session: int, code: str, reset: bool = False):
        escaped_code = shlex.quote(code)
        command = f"node /exe/node_eval.js {escaped_code}"
        return await self.terminal_session(session, command, reset)

    async def execute_terminal_command(self, session: int, command: str, reset: bool = False):
        return await self.terminal_session(session, command, reset)

    async def terminal_session(self, session: int, command: str, reset: bool = False):
        await self.agent.handle_intervention()
        for i in range(2):
            try:
                if reset:
                    await self.reset_terminal()
                if session not in self.state.shells:
                    if getattr(self.agent.config, 'code_exec_ssh_enabled', False):
                        pswd = (
                            self.agent.config.code_exec_ssh_pass
                            if self.agent.config.code_exec_ssh_pass
                            else self.root_password
                        )
                        shell = SSHInteractiveSession(
                            self.agent.context.log,
                            self.agent.config.code_exec_ssh_addr,
                            self.agent.config.code_exec_ssh_port,
                            self.agent.config.code_exec_ssh_user,
                            pswd,
                        )
                    else:
                        shell = LocalInteractiveSession()
                    self.state.shells[session] = shell
                    await shell.connect()
                self.state.shells[session].send_command(command)
                PrintStyle(
                    background_color="white", font_color="#1B4F72", bold=True
                ).print(f"{self.agent.agent_name} code execution output")
                return await self.get_terminal_output(session)
            except Exception as e:
                if i == 1:
                    PrintStyle.error(str(e))
                    await self.prepare_state(reset=True)
                    continue
                else:
                    raise e

    async def get_terminal_output(
        self,
        session=0,
        reset_full_output=True,
        first_output_timeout=30,
        between_output_timeout=15,
        max_exec_timeout=180,
        sleep_time=0.1,
    ):
        prompt_patterns = [
            re.compile(r"\\(venv\\).+[$#] ?$"),
            re.compile(r"root@[^:]+:[^#]+# ?$"),
            re.compile(r"[a-zA-Z0-9_.-]+@[^:]+:[^$#]+[$#] ?$"),
        ]
        start_time = time.time()
        last_output_time = start_time
        full_output = ""
        truncated_output = ""
        got_output = False
        while True:
            await asyncio.sleep(sleep_time)
            full_output, partial_output = await self.state.shells[session].read_output(
                timeout=3, reset_full_output=reset_full_output
            )
            reset_full_output = False
            await self.agent.handle_intervention()
            now = time.time()
            if partial_output:
                PrintStyle(font_color="#85C1E9").stream(partial_output)
                truncated_output = truncate_text(
                    agent=self.agent, output=full_output, threshold=10000
                )
                self.log.update(content=truncated_output)
                last_output_time = now
                got_output = True
                last_lines = truncated_output.splitlines()[-3:] if truncated_output else []
                for line in last_lines:
                    for pat in prompt_patterns:
                        if pat.search(line.strip()):
                            PrintStyle.info(
                                "Detected shell prompt, returning output early."
                            )
                            return truncated_output
            if now - start_time > max_exec_timeout:
                sysinfo = self.agent.read_prompt(
                    "fw.code.max_time.md", timeout=max_exec_timeout
                )
                response = self.agent.read_prompt("fw.code.info.md", info=sysinfo)
                if truncated_output:
                    response = truncated_output + "\n\n" + response
                PrintStyle.warning(sysinfo)
                self.log.update(content=response)
                return response
            if not got_output:
                if now - start_time > first_output_timeout:
                    sysinfo = self.agent.read_prompt(
                        "fw.code.no_out_time.md", timeout=first_output_timeout
                    )
                    response = self.agent.read_prompt("fw.code.info.md", info=sysinfo)
                    PrintStyle.warning(sysinfo)
                    self.log.update(content=response)
                    return response
            else:
                if now - last_output_time > between_output_timeout:
                    sysinfo = self.agent.read_prompt(
                        "fw.code.pause_time.md", timeout=between_output_timeout
                    )
                    response = self.agent.read_prompt("fw.code.info.md", info=sysinfo)
                    if truncated_output:
                        response = truncated_output + "\n\n" + response
                    PrintStyle.warning(sysinfo)
                    self.log.update(content=response)
                    return response

    async def reset_terminal(self, session=0, reason: str | None = None):
        if reason:
            PrintStyle(font_color="#FFA500", bold=True).print(
                f"Resetting terminal session {session}... Reason: {reason}"
            )
        else:
            PrintStyle(font_color="#FFA500", bold=True).print(
                f"Resetting terminal session {session}..."
            )
        await self.prepare_state(reset=True, session=session)
        response = self.agent.read_prompt(
            "fw.code.info.md", info=self.agent.read_prompt("fw.code.reset.md")
        )
        self.log.update(content=response)
        return response