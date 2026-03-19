import requests

REPO = "JayeshSRathod/nse-scanner"
FILE_PATH = "telegram_last_scan.json"
BRANCH = "main"


def fetch_json():
    url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{FILE_PATH}"

    response = requests.get(url)

    if response.status_code == 200:
        return response.json()
    else:
        print("❌ Failed to fetch JSON")
        return None