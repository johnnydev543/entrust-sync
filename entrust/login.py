"""登入頁帳密自動填入（explore.py 舊版精準 selector 已與
entrust_sync.py 的萬用 fallback chain 漂移，統一採用 fallback chain —
舊 ASP.NET 網站的單一 selector 不保證永遠有效）。"""

from dotenv import load_dotenv

from entrust.config import SCRIPT_DIR


def load_credentials() -> tuple[str, str]:
    # 專案 .env 是此工具明確指定的帳密來源；覆蓋 shell 中可能殘留的空值。
    load_dotenv(SCRIPT_DIR / ".env", override=True)
    import os
    return os.getenv("ENTRUST_ACCOUNT", ""), os.getenv("ENTRUST_PASSWORD", "")


def fill_credentials(page, account: str, password: str):
    """在登入頁自動填入帳號與密碼（依序嘗試多個 selector）。"""
    for sel in ['input[name*="id"]', 'input[name*="account"]',
                'input[type="text"]', 'input[id*="ID"]']:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                el.click(); el.fill(account)
                print("   ✓ 帳號"); break
        except Exception:
            continue
    for sel in ['input[name*="pwd"]', 'input[name*="password"]',
                'input[type="password"]']:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                el.click(); el.fill(password)
                print("   ✓ 密碼"); break
        except Exception:
            continue


def click_login_button(page):
    """點擊登入按鈕（依序嘗試多個 selector）。"""
    for sel in ['button:has-text("登入")', 'input[type="submit"]',
                'a:has-text("登入")', '#btnLogin']:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click(); print("   ✓ 登入"); break
        except Exception:
            continue
