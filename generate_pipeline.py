import os
import json
import requests
from pathlib import Path

# === CONFIG ===
AGENT_ZERO_URL = "http://localhost:50001/message"
AUTH_HEADER = {
    "Authorization": "Basic YWRtaW46YWRtaW4xMjM=",  # Replace if needed
    "Content-Type": "application/json"
}
TARGET_YML = Path(".github/workflows/deploy.yml")

# === Read project files ===
def read_file(path):
    if not os.path.exists(path): return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

app_files = {
    "app.py": read_file("app.py"),
    "requirements.txt": read_file("requirements.txt"),
    "Dockerfile": read_file("Dockerfile"),
    "tests/test_app.py": read_file("tests/test_app.py"),
    "docker-compose.prod.yml": read_file("docker-compose.prod.yml")
}

# === Build payload ===
files_combined = ""
for name, content in app_files.items():
    if content.strip():
        files_combined += f"\n\n# FILE: {name}\n{content}"

payload = {
    "task": f"Analyze the following Python Flask project and generate only the deploy.yml CI/CD pipeline in GitHub Actions YAML. Use Docker, pytest, and SSH deployment. Here's the project:\n{files_combined}",
    "output_format": "text"
}


# === Send request ===
print("🔄 Sending files to Agent-Zero...")
resp = requests.post(AGENT_ZERO_URL, headers=AUTH_HEADER, data=json.dumps(payload))

if resp.status_code != 200:
    print(f"❌ Error: {resp.status_code} - {resp.text}")
    exit(1)

message = resp.json().get("message", "")

# === Extract only YAML block ===
yaml_lines = []
in_block = False
for line in message.splitlines():
    if line.strip().startswith("```yaml"):
        in_block = True
        continue
    if line.strip().startswith("```") and in_block:
        break
    if in_block:
        yaml_lines.append(line)

if not yaml_lines:
    print("⚠️ No YAML block found in response.")
    exit(1)

# === Write YAML to deploy.yml ===
os.makedirs(TARGET_YML.parent, exist_ok=True)
with open(TARGET_YML, "w", encoding="utf-8") as f:
    f.write("\n".join(yaml_lines))

print(f"✅ CI/CD workflow written to {TARGET_YML}")
