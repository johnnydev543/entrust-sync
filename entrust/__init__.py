"""華南永昌證券同步 — 共用模組。

三支腳本（entrust_sync.py / explore.py / debug_popup.py）原本各自持有
一份複製貼上的邏輯（常數、alert/popup 處理、表格擷取、瀏覽器啟動）。
此套件把它們收斂成單一來源；各腳本只保留自己的流程差異。

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
    OUTPUT_DIR,
    SCRIPT_DIR,
    USER_DATA_DIR,
)
from entrust.handlers import alert_log, on_dialog, on_popup, reset_alert_log

__all__ = [
    "DEFAULT_TIMEOUT",
    "LAUNCH_ARGS",
    "LOGIN_URL",
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