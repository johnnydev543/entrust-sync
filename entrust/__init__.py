"""華南永昌證券同步 — 共用模組。

互動同步程式與 popup 診斷工具共用常數、alert/popup 處理、表格擷取與
瀏覽器啟動邏輯，避免 selector 與憑證流程在不同入口間漂移。

搬移原則：逐字搬移、不改行為（見 AGENTS.md 關鍵規則 3–5）。
"""

from entrust.browser import launch_browser
from entrust.capture import (
    capture_aggregate_inventory,
    capture_all_tables,
    download_aggregate_inventory_xls,
    save_step,
)
from entrust.config import (
    DEFAULT_TIMEOUT,
    LAUNCH_ARGS,
    LOGIN_URL,
    MAIN_URL,
    OUTPUT_DIR,
    SCRIPT_DIR,
    USER_DATA_DIR,
)
from entrust.handlers import alert_log, on_dialog, on_popup, reset_alert_log

__all__ = [
    "DEFAULT_TIMEOUT",
    "LAUNCH_ARGS",
    "LOGIN_URL",
    "MAIN_URL",
    "OUTPUT_DIR",
    "SCRIPT_DIR",
    "USER_DATA_DIR",
    "alert_log",
    "capture_aggregate_inventory",
    "capture_all_tables",
    "download_aggregate_inventory_xls",
    "launch_browser",
    "on_dialog",
    "on_popup",
    "reset_alert_log",
    "save_step",
]
