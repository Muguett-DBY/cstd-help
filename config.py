import os

ACCOUNT_ID = 173776719

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DOTA_REVIEW_DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.environ.get("DOTA_REVIEW_DB_PATH", os.path.join(DATA_DIR, "dota2.db"))

REPORT_DIR = os.environ.get("DOTA_REVIEW_REPORT_DIR", r"C:\Users\12031\Desktop\REVIEW_REPORT")

STRATZ_API_KEY_PATH = r"C:\Users\12031\Desktop\STRATZ_API.txt"

def _read_stratz_key():
    try:
        with open(STRATZ_API_KEY_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

STRATZ_API_KEY = os.environ.get("STRATZ_API_KEY", "").strip() or _read_stratz_key()

OPENDOTA_BASE_URL = "https://api.opendota.com/api"
STRATZ_GRAPHQL_URL = "https://api.stratz.com/graphql"
