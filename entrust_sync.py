#!/usr/bin/env python3
"""
華南永昌證券 — 持股 & 交易紀錄自動同步
==========================================

在本地電腦跑的 Playwright 腳本。
- 自動登入華南永昌數位網
- 抓取持股明細與交易紀錄
- 存成 JSON 檔案

⚠️ 帳密只存在你自己的電腦上，OTP 需手動輸入。
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─── 路徑設定 ───────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ─── 登入頁面 ───────────────────────────────────────────────
LOGIN_URL = "https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx"

# ─── 等待設定 ───────────────────────────────────────────────
DEFAULT_TIMEOUT = 30_000  # 30 秒
OTP_WAIT_TIMEOUT = 120_000  # OTP 等待 2 分鐘


def load_credentials() -> tuple[str, str]:
    """從 .env 或環境變數讀取帳密"""
    load_dotenv(SCRIPT_DIR / ".env")
    account = os.getenv("ENTRUST_ACCOUNT", "")
    password = os.getenv("ENTRUST_PASSWORD", "")
    return account, password


def login(page, account: str, password: str, headed: bool = True):
    """
    登入華南永昌數位網。
    如果帳密為空，會在瀏覽器中等待手動輸入。
    OTP 一定需要手動輸入。
    """
    print("🌐 正在開啟華南永昌數位網登入頁...")
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=DEFAULT_TIMEOUT)
    page.wait_for_timeout(2000)

    # 如果有帳密，自動填入；否則等使用者手動輸入
    if account and password:
        print("📝 自動填入帳號密碼...")
        try:
            # 嘗試找到帳號輸入框（身分證字號或帳號）
            # 華南永昌登入頁可能有多種欄位名稱，逐一嘗試
            account_selectors = [
                'input[name*="id"]',
                'input[name*="account"]',
                'input[name*="ID"]',
                'input[type="text"]',
                'input[id*="txtID"]',
                'input[id*="txtAccount"]',
            ]
            password_selectors = [
                'input[name*="pwd"]',
                'input[name*="password"]',
                'input[name*="PWD"]',
                'input[type="password"]',
                'input[id*="txtPWD"]',
                'input[id*="txtPassword"]',
            ]

            # 填帳號
            filled = False
            for sel in account_selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=3000):
                        el.click()
                        el.fill(account)
                        filled = True
                        print(f"   ✓ 帳號已填入 (selector: {sel})")
                        break
                except Exception:
                    continue
            if not filled:
                print("   ⚠️ 找不到帳號欄位，請手動輸入")

            # 填密碼
            filled = False
            for sel in password_selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=3000):
                        el.click()
                        el.fill(password)
                        filled = True
                        print(f"   ✓ 密碼已填入")
                        break
                except Exception:
                    continue
            if not filled:
                print("   ⚠️ 找不到密碼欄位，請手動輸入")

            # 嘗試選擇「證券」認證方式
            try:
                sec_tab = page.locator('text=證券').first
                if sec_tab.is_visible(timeout=3000):
                    sec_tab.click()
                    print("   ✓ 已選擇證券認證")
            except Exception:
                pass

            # 點擊登入按鈕
            login_selectors = [
                'button:has-text("登入")',
                'input[type="submit"]',
                'a:has-text("登入")',
                '#btnLogin',
                'input[id*="btnLogin"]',
            ]
            for sel in login_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=3000):
                        btn.click()
                        print("   ✓ 已點擊登入")
                        break
                except Exception:
                    continue

        except Exception as e:
            print(f"   ⚠️ 自動填入失敗: {e}")
            print("   → 請手動在瀏覽器中輸入帳密並登入")

    # ── 等待 OTP 或登入完成 ──
    print("\n🔑 請在瀏覽器中完成登入（包含 OTP 驗證）...")
    if not headed:
        print("   ⚠️ 無頭模式下無法手動輸入 OTP，請改用 --headed")

    # 等待登入成功的特徵：URL 變化或特定元素出現
    # 華南永昌登入後通常會跳轉到主頁面
    print("   ⏳ 等待登入完成...")
    try:
        page.wait_for_url("**/Main**", timeout=OTP_WAIT_TIMEOUT)
    except PlaywrightTimeout:
        try:
            page.wait_for_url("**/Home**", timeout=5000)
        except PlaywrightTimeout:
            try:
                page.wait_for_url("**/default**", timeout=5000)
            except PlaywrightTimeout:
                # 最後手段：等使用者確認
                print("   ⏳ 未偵測到登入跳轉，請確認已登入後按 Enter...")
                if headed:
                    input("   → 登入完成後按 Enter 繼續...")

    print("✅ 登入成功！")
    page.wait_for_timeout(2000)


def navigate_to_holdings(page):
    """導航到持股明細頁面"""
    print("📊 正在前往持股查詢頁面...")

    # 嘗試多種可能的選單路徑
    # 華南永昌的選單結構可能變動，這裡用多種策略
    strategies = [
        # 策略 1：直接點選單文字
        {"desc": "點擊帳務選單", "selectors": [
            'text=帳務',
            'text=帳務查詢',
            'text=庫存查詢',
            'text=持股',
            'text=持股明細',
        ]},
        # 策略 2：用 link text
        {"desc": "用連結導航", "selectors": [
            'a:has-text("帳務")',
            'a:has-text("庫存")',
            'a:has-text("持股明細")',
        ]},
    ]

    for strategy in strategies:
        for sel in strategy["selectors"]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=3000):
                    el.click()
                    page.wait_for_timeout(1000)
                    print(f"   ✓ {strategy['desc']}: {sel}")
                    break
            except Exception:
                continue

    # 嘗試直接用 URL 導航（如果知道持股頁面的直接連結）
    # 這需要實際探索後才能確定
    page.wait_for_timeout(2000)


def scrape_holdings(page) -> list[dict]:
    """抓取持股明細"""
    print("📋 正在抓取持股明細...")

    holdings = []

    # 嘗試找到表格
    try:
        table = page.locator("table").first
        if table.is_visible(timeout=5000):
            rows = table.locator("tr")
            headers = []

            # 讀取表頭
            header_row = rows.first
            for th in header_row.locator("th, td").all():
                headers.append(th.text_content().strip())

            # 讀取資料行
            for i in range(1, rows.count()):
                row = rows.nth(i)
                cells = row.locator("td").all()
                if cells:
                    row_data = {}
                    for j, cell in enumerate(cells):
                        key = headers[j] if j < len(headers) else f"col_{j}"
                        row_data[key] = cell.text_content().strip()
                    if row_data:
                        holdings.append(row_data)

            print(f"   ✓ 抓到 {len(holdings)} 筆持股資料")
        else:
            print("   ⚠️ 找不到持股表格，嘗試截圖除錯...")
            page.screenshot(path=str(OUTPUT_DIR / "debug_holdings.png"))

    except Exception as e:
        print(f"   ⚠️ 抓取持股失敗: {e}")
        page.screenshot(path=str(OUTPUT_DIR / "debug_holdings_error.png"))

    return holdings


def navigate_to_transactions(page):
    """導航到交易紀錄頁面"""
    print("📜 正在前往交易查詢頁面...")

    selectors = [
        'text=交易查詢',
        'text=委託查詢',
        'text=成交查詢',
        'text=歷史成交',
        'a:has-text("交易")',
        'a:has-text("成交")',
    ]

    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=3000):
                el.click()
                page.wait_for_timeout(1000)
                break
        except Exception:
            continue

    page.wait_for_timeout(2000)


def scrape_transactions(page) -> list[dict]:
    """抓取交易紀錄"""
    print("📋 正在抓取交易紀錄...")

    transactions = []

    try:
        table = page.locator("table").first
        if table.is_visible(timeout=5000):
            rows = table.locator("tr")
            headers = []

            header_row = rows.first
            for th in header_row.locator("th, td").all():
                headers.append(th.text_content().strip())

            for i in range(1, rows.count()):
                row = rows.nth(i)
                cells = row.locator("td").all()
                if cells:
                    row_data = {}
                    for j, cell in enumerate(cells):
                        key = headers[j] if j < len(headers) else f"col_{j}"
                        row_data[key] = cell.text_content().strip()
                    if row_data:
                        transactions.append(row_data)

            print(f"   ✓ 抓到 {len(transactions)} 筆交易紀錄")
        else:
            print("   ⚠️ 找不到交易表格")
            page.screenshot(path=str(OUTPUT_DIR / "debug_transactions.png"))

    except Exception as e:
        print(f"   ⚠️ 抓取交易紀錄失敗: {e}")

    return transactions


def save_data(holdings: list[dict], transactions: list[dict]):
    """儲存抓取的資料"""
    today = date.today().isoformat()

    holdings_file = OUTPUT_DIR / f"holdings_{today}.json"
    transactions_file = OUTPUT_DIR / f"transactions_{today}.json"

    with open(holdings_file, "w", encoding="utf-8") as f:
        json.dump({
            "date": today,
            "source": "華南永昌證券",
            "count": len(holdings),
            "holdings": holdings
        }, f, ensure_ascii=False, indent=2)
    print(f"   💾 持股明細已存: {holdings_file}")

    with open(transactions_file, "w", encoding="utf-8") as f:
        json.dump({
            "date": today,
            "source": "華南永昌證券",
            "count": len(transactions),
            "transactions": transactions
        }, f, ensure_ascii=False, indent=2)
    print(f"   💾 交易紀錄已存: {transactions_file}")

    return holdings_file, transactions_file


def interactive_mode(page):
    """
    互動模式：讓使用者自己操作瀏覽器登入，
    腳本只負責等待和抓取。
    """
    print("\n" + "=" * 50)
    print("🔑 互動模式 — 請在瀏覽器中完成登入")
    print("=" * 50)
    print()
    print("步驟：")
    print("  1. 在瀏覽器中輸入帳號密碼")
    print("  2. 輸入 OTP 驗證碼")
    print("  3. 登入成功後，回到終端按 Enter")
    print()

    input("   → 登入完成後按 Enter 繼續...")

    # 登入後截圖確認
    page.screenshot(path=str(OUTPUT_DIR / "after_login.png"))
    print("   ✓ 已截圖確認登入狀態")


def main():
    parser = argparse.ArgumentParser(description="華南永昌持股同步工具")
    parser.add_argument("--auto", action="store_true", help="自動模式（需設定 .env）")
    parser.add_argument("--headed", action="store_true", default=True, help="顯示瀏覽器（預設）")
    parser.add_argument("--headless", action="store_true", help="無頭模式（不推薦，OTP需手動輸入）")
    parser.add_argument("--debug", action="store_true", help="除錯模式，每步截圖")
    args = parser.parse_args()

    headed = not args.headless
    account, password = "", ""

    if args.auto:
        account, password = load_credentials()
        if not account or not password:
            print("❌ 自動模式需要設定 .env 檔案（請複製 .env.example 並填入帳密）")
            sys.exit(1)
        print(f"   ✓ 已從 .env 讀取帳號: {account[:3]}***")

    print()
    print("🏦 華南永昌持股同步工具")
    print("=" * 40)

    with sync_playwright() as p:
        print("🚀 啟動瀏覽器...")
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # ── 登入 ──
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=DEFAULT_TIMEOUT)

            if args.auto and account and password:
                # 自動填入帳密，但 OTP 仍需手動
                login(page, account, password, headed=headed)
            else:
                # 完全互動模式
                interactive_mode(page)

            if args.debug:
                page.screenshot(path=str(OUTPUT_DIR / "debug_01_after_login.png"))

            # ── 抓取持股 ──
            navigate_to_holdings(page)
            if args.debug:
                page.screenshot(path=str(OUTPUT_DIR / "debug_02_holdings_page.png"))
            holdings = scrape_holdings(page)

            # ── 抓取交易紀錄 ──
            navigate_to_transactions(page)
            if args.debug:
                page.screenshot(path=str(OUTPUT_DIR / "debug_03_transactions_page.png"))
            transactions = scrape_transactions(page)

            # ── 儲存 ──
            if holdings or transactions:
                h_file, t_file = save_data(holdings, transactions)
                print()
                print("📊 同步完成！")
                print(f"   持股: {len(holdings)} �筆")
                print(f"   交易: {len(transactions)} 筆")
                print()
                print("📁 輸出檔案：")
                print(f"   {h_file}")
                print(f"   {t_file}")
            else:
                print()
                print("⚠️ 未抓取到任何資料")
                print("   可能原因：")
                print("   1. 登入未成功")
                print("   2. 網頁結構變動")
                print("   3. 需要手動導航到正確頁面")
                print()
                print("💡 建議用 --debug 模式重新執行，檢查截圖")
                page.screenshot(path=str(OUTPUT_DIR / "debug_final.png"))

        except Exception as e:
            print(f"\n❌ 發生錯誤: {e}")
            page.screenshot(path=str(OUTPUT_DIR / "error_screenshot.png"))
            print(f"   已截圖: {OUTPUT_DIR / 'error_screenshot.png'}")
            raise

        finally:
            context.close()
            browser.close()
            print("\n🔒 瀏覽器已關閉")


if __name__ == "__main__":
    main()