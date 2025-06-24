import asyncio
import subprocess

async def async_subprocess(command: str, check: bool = True) -> tuple[str, str, int]:
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return stdout.decode(), stderr.decode(), process.returncode