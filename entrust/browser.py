"""瀏覽器啟動（Edge → Chromium fallback）+ addInitScript 注入。

init script 的行為是刻意的（見 AGENTS.md 關鍵規則 3–5）：
- navigator.webdriver 必須為 false，否則客戶專區會移除 ElectricCA 等路由
- alert/confirm 覆蓋讓頁面 JS 不會死鎖
- window.open 純記錄、必須回傳真正的 Window（回傳 null 會弄壞憑證表單提交）
"""

from entrust.config import LAUNCH_ARGS, USER_DATA_DIR
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


def launch_browser(playwright):
    """以 persistent context 啟動瀏覽器，優先 Edge（憑證元件需要）。

    回傳 (context, browser_channel)。
    """
    browser_channel = "msedge"
    try:
        print("🚀 啟動瀏覽器（嘗試 Edge）...")
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            channel=browser_channel,
            headless=False,
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
            args=LAUNCH_ARGS,
        )
    except Exception as e:
        print(f"⚠️ Edge 啟動失敗（{e}），改用 Chromium...")
        browser_channel = "chromium"
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
            args=LAUNCH_ARGS,
        )
    print(f"   ✅ 使用瀏覽器: {browser_channel}")

    # addInitScript 在每個頁面的任何 JS 執行前就注入，比 page.evaluate()
    # 更可靠（不會被頁面導航清除）。
    context.add_init_script(INIT_SCRIPT)
    print("   ✅ addInitScript 已注入（alert/confirm/window.open 覆蓋）")

    context.on("page", on_popup)
    # 用 context.on("dialog") 處理所有頁面（含 iframe）的 alert
    context.on("dialog", on_dialog)

    return context, browser_channel