import requests
import base64
import os

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "JayeshSRathod/nse-scanner"   # change if needed
FILE_PATH = "telegram_last_scan.json"
BRANCH = "main"


def push_json_to_github():
    with open(FILE_PATH, "rb") as f:
        content = f.read()

    encoded = base64.b64encode(content).decode()

    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Get current file SHA (required for update)
    response = requests.get(url, headers=headers)
    sha = response.json().get("sha")

    data = {
        "message": "update scan results",
        "content": encoded,
        "branch": BRANCH
    }

    if sha:
        data["sha"] = sha

    r = requests.put(url, json=data, headers=headers)

    if r.status_code in [200, 201]:
        print("✅ JSON pushed to GitHub")
    else:
        print("❌ GitHub push failed:", r.text)