import os

ACCOUNT_ID = 173776719

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "dota2.db")

REPORT_DIR = r"C:\Users\12031\Desktop\REVIEW_REPORT"

STRATZ_API_KEY_PATH = r"C:\Users\12031\Desktop\STRATZ_API.txt"

def _read_stratz_key():
    try:
        with open(STRATZ_API_KEY_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

STRATZ_API_KEY = _read_stratz_key()

OPENCODE_AI_BASE_URL = "https://opencode.ai/zen/go/v1"
OPENCODE_AI_MODEL = "mimo-v2.5"

TOKEN_FILE_PATH = r"E:\DEV\codex-tools\TOKEN.txt"

def _read_opencode_key():
    try:
        with open(TOKEN_FILE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENCODE_GO_API_KEY="):
                    return line.split("=", 1)[1]
    except FileNotFoundError:
        return ""
    return ""

OPENCODE_AI_API_KEY = _read_opencode_key()
ENABLE_FREEFORM_AI = os.environ.get("DOTA_REVIEW_ALLOW_AI", "").lower() in ("1", "true", "yes")

OPENDOTA_BASE_URL = "https://api.opendota.com/api"
STRATZ_GRAPHQL_URL = f"https://api.stratz.com/graphql?key={STRATZ_API_KEY}"
