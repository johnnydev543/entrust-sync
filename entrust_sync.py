#!/usr/bin/env python3
"""
華南永昌持股同步 — 自動模式 v3
=================================

v3: 使用 persistent context，憑證只需安裝一次

使用方式：
  1. 第一次：python entrust_sync.py
     → 手動完成登入 + 憑證申請
  2. 之後：python entrust_sync.py --auto
     → 自動填入帳密（OTP 仍需手動）
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
USER_DATA_DIR = SCRIPT_DIR / "browser_profile"

LOGIN_URL = "https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx"
DEFAULT_TIMEOUT = 30_000


def load_credentials() -> tuple[str, str]:
    load_dotenv(SCRIPT_DIR / ".env")
    account = os.getenv("ENTRUST_ACCOUNT", "")
    password = os.getenv("ENTRUST_PASSWORD", "")
    return account, password


def capture_all_tables(page) -> list[dict]:
    """抓取頁面上所有表格（含 iframe）"""
    tables_data = []

    for t_idx, table in enumerate(page.locator("table").all()):
        try:
            rows = table.locator("tr").all()
            if not rows:
                continue
            headers = [cell.text_content().strip() for cell in rows[0].locator("th, td").all()]
            data_rows = []
            for row in rows[1:]:
                cells = row.locator("td").all()
                if not cells:
                    continue
                row_data = {}
                for j, cell in enumerate(cells):
                    key = headers[j] if j < len(headers) else f"col_{j}"
                    row_data[key] = cell.text_content().strip()
                if row_data:
                    data_rows.append(row_data)
            tables_data.append({
                "table_index": t_idx,
                "headers": headers,
                "row_count": len(data_rows),
                "data": data_rows,
                "source": "main",
            })
        except Exception:
            pass

    for i, frame in enumerate(page.frames):
        if frame == page.main_frame:
            continue
        try:
            for t_idx, table in enumerate(frame.locator("table").all()):
                try:
                    rows = table.locator("tr").all()
                    if not rows:
                        continue
                    headers = [cell.text_content().strip() for cell in rows[0].locator("th, td").all()]
                    data_rows = []
                    for row in rows[1:]:
                        cells = row.locator("td").all()
                        if not cells:
                            continue
                        row_data = {}
                        for j, cell in enumerate(cells):
                            key = headers[j] if j < len(headers) else f"col_{j}"
                            row_data[key] = cell.text_content().strip()
                        if row_data:
                            data_rows.append(row_data)
                    tables_data.append({
                        "table_index": t_idx,
                        "headers": headers,
                        "row_count": len(data_rows),
                        "data": data_rows,
                        "source": f"iframe_{i}",
                    })
                except Exception:
                    pass
        except Exception:
            pass

    return tables_data


def main():
    parser = argparse.ArgumentParser(description="華南永昌持股同步 v3")
    parser.add_argument("--auto", action="store_true", help="自動填入帳密（需 .env）")
    parser.add_argument("--debug", action="store_true", help="除錯模式")
    args = parser.parse_args()

    account, password = "", ""
    if args.auto:
        account, password = load_credentials()
        if not account or not password:
            print("❌ 自動模式需要 .env 檔案")
            sys.exit(1)
        print(f"   ✓ 帳號: {account[:3]}***")

    print()
    print("🏦 華南永昌持股同步 v3")
    print("=" * 40)
    print("🔑 persistent context：憑證只需安裝一次")
    print()

    with sync_playwright() as p:
        print("🚀 啟動瀏覽器...")
        print(f"   Profile: {USER_DATA_DIR}")

        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            print(f"🌐 開啟: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=DEFAULT_TIMEOUT)
            page.wait_for_timeout(2000)

            # 檢查是否已登入
            current_url = page.url.lower()
            if "login" not in current_url:
                print("✅ 可能已經登入，跳過登入步驟")
            else:
                if args.auto and account and password:
                    print("📝 自動填入帳密...")
                    # 帳號
                    for sel in ['input[name*="id"]', 'input[name*="account"]',
                                'input[type="text"]', 'input[id*="ID"]', 'input[id*="Account"]']:
                        try:
                            el = page.locator(sel).first
                            if el.is_visible(timeout=2000):
                                el.click()
                                el.fill(account)
                                print(f"   ✓ 帳號已填入")
                                break
                        except Exception:
                            continue

                    # 密碼
                    for sel in ['input[name*="pwd"]', 'input[name*="password"]',
                                'input[type="password"]', 'input[id*="PWD"]', 'input[id*="Password"]']:
                        try:
                            el = page.locator(sel).first
                            if el.is_visible(timeout=2000):
                                el.click()
                                el.fill(password)
                                print(f"   ✓ 密碼已填入")
                                break
                        except Exception:
                            continue

                    # 登入
                    for sel in ['button:has-text("登入")', 'input[type="submit"]',
                                'a:has-text("登入")', '#btnLogin']:
                        try:
                            btn = page.locator(sel).first
                            if btn.is_visible(timeout=2000):
                                btn.click()
                                print("   ✓ 已點擊登入")
                                break
                        except Exception:
                            continue

                print("\n🔑 請在瀏覽器中完成登入（OTP + 憑證）")
                print("   ⚠️ 憑證視窗是 Windows 元件，腳本無法自動操作")
                print("   💡 請手動在瀏覽器中處理，之後會保存在 profile 裡")
                input("   👉 登入完成後按 Enter...")

            page.screenshot(path=str(OUTPUT_DIR / "after_login.png"))

            # ── 抓取持股 ──
            print("\n📊 請導航到「持股明細」或「庫存查詢」頁面")
            input("   👉 到達後按 Enter...")
            page.screenshot(path=str(OUTPUT_DIR / f"holdings.png"))
            holdings_tables = capture_all_tables(page)

            # ── 抓取交易 ──
            print("\n📜 請導航到「交易紀錄」或「成交查詢」頁面")
            input("   👉 到達後按 Enter...")
            page.screenshot(path=str(OUTPUT_DIR / f"transactions.png"))
            transactions_tables = capture_all_tables(page)

            # ── 儲存 ──
            today = date.today().isoformat()

            all_tables = {"holdings": holdings_tables, "transactions": transactions_tables}
            for name, tables in all_tables.items():
                filepath = OUTPUT_DIR / f"{name}_{today}.json"
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump({
                        "date": today,
                        "source": "華南永昌證券",
                        "page_url": page.url,
                        "tables": tables,
                    }, f, ensure_ascii=False, indent=2)
                print(f"   💾 {filepath}")

            # 額外
            while True:
                extra = input("\n🎯 其他頁面？（名稱 / Enter 結束）: ").strip()
                if not extra:
                    break
                input(f"   導航到「{extra}」後按 Enter...")
                page.screenshot(path=str(OUTPUT_DIR / f"{extra}.png"))
                tables = capture_all_tables(page)
                filepath = OUTPUT_DIR / f"{extra}_{today}.json"
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump({"date": today, "tables": tables}, f, ensure_ascii=False, indent=2)

        except KeyboardInterrupt:
            print("\n⚠️ 中斷")
        except Exception as e:
            print(f"\n❌ 錯誤: {e}")
            page.screenshot(path=str(OUTPUT_DIR / "error.png"))

        finally:
            context.close()
            print("\n🔒 瀏覽器已關閉（profile 已保存）")
            print(f"   下次啟動會自動帶入憑證: {USER_DATA_DIR}")


if __name__ == "__main__":
    main()