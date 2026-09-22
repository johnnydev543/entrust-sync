"""共用路徑與網站常數（原三支腳本頂部的常數區塊）。"""

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
USER_DATA_DIR = SCRIPT_DIR / "browser_profile"
SESSION_COOKIES_FILE = USER_DATA_DIR / "session_cookies.json"

LOGIN_URL = "https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx"
MAIN_URL = "https://eztrade.entrust.com.tw/hnsweb/default.aspx"
DEFAULT_TIMEOUT = 30_000

LAUNCH_ARGS = [
    "--restore-last-session",
    "--disable-popup-blocking",
    "--disable-features=PopupBlocker",
    "--disable-blink-features=AutomationControlled",
]
