"""Chromium persistent context 啟動、session cookie 保存與 init script 注入。

init script 的行為是刻意的（見 AGENTS.md 關鍵規則 3–5）：
- navigator.webdriver 必須為 false，否則客戶專區會移除 ElectricCA 等路由
- alert/confirm 覆蓋讓頁面 JS 不會死鎖
- window.open 純記錄、必須回傳真正的 Window（回傳 null 會弄壞憑證表單提交）
"""

import json
import os

from entrust.config import LAUNCH_ARGS, SESSION_COOKIES_FILE, USER_DATA_DIR
from entrust.handlers import on_dialog, on_popup

INIT_SCRIPT = """
    // 客戶專區會在 navigator.webdriver 為 true 時移除 ElectricCA
    // 等功能路由，結果看起來像站方 404。
    Object.defineProperty(Navigator.prototype, 'webdriver', {
        get: () => false,
        configurable: true
    });
    window.alert = function(msg) {
        console.log('[ALERT BLOCKED] ' + String(msg));
        return undefined;
    };
    window.confirm = function(msg) {
        console.log('[CONFIRM BLOCKED] ' + String(msg));
        return true;
    };
    const __originalOpen = window.open;
    window.open = function(...args) {
        const url = args[0] || '';
        console.log('[WINDOW.OPEN] ' + url);
        // 純記錄，不阻擋任何視窗。登入、session 轉接與憑證頁都可能
        // 依賴 window.open 回傳的 Window 物件。
        return __originalOpen.apply(this, args);
    };
"""


def restore_session_cookies(context):
    """還原正常關閉前保存的 session cookies；失敗時仍允許瀏覽器啟動。"""
    if not SESSION_COOKIES_FILE.exists():
        return 0
    try:
        cookies = json.loads(SESSION_COOKIES_FILE.read_text(encoding="utf-8"))
        if not isinstance(cookies, list):
            raise ValueError("cookie state 格式錯誤")
        if cookies:
            context.add_cookies(cookies)
        print(f"   ✅ 已還原 {len(cookies)} 個 session cookies")
        return len(cookies)
    except Exception as exc:
        print(f"⚠️ 無法還原 session cookies（{exc}）")
        return 0


def save_session_cookies(context):
    """原子寫入 cookies 到 persistent profile，權限限制為目前使用者。"""
    try:
        cookies = context.cookies()
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = SESSION_COOKIES_FILE.with_suffix(".json.tmp")
        temp_file.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
        os.chmod(temp_file, 0o600)
        temp_file.replace(SESSION_COOKIES_FILE)
        return len(cookies)
    except Exception as exc:
        print(f"⚠️ 無法保存 session cookies（{exc}）")
        return 0


def launch_browser(playwright):
    """以 persistent context 啟動 Chromium，並還原上次保存的 session。

    回傳 (context, browser_channel)。
    """
    browser_channel = "chromium"
    print("🚀 啟動 Chromium...")
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=False,
        viewport={"width": 1920, "height": 1080},
        accept_downloads=True,
        args=LAUNCH_ARGS,
    )
    restore_session_cookies(context)
    print(f"   ✅ 使用瀏覽器: {browser_channel}")

    # addInitScript 在每個頁面的任何 JS 執行前就注入，比 page.evaluate()
    # 更可靠（不會被頁面導航清除）。
    context.add_init_script(INIT_SCRIPT)
    print("   ✅ addInitScript 已注入（alert/confirm/window.open 覆蓋）")

    context.on("page", on_popup)
    # 用 context.on("dialog") 處理所有頁面（含 iframe）的 alert
    context.on("dialog", on_dialog)

    return context, browser_channel
