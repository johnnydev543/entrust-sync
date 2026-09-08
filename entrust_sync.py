#!/usr/bin/env python3
"""
華南永昌持股同步 — 自動模式 v5
=================================

v5: 共用邏輯收斂到 entrust/ 套件（常數、alert/popup handler、表格擷取、
    瀏覽器啟動、帳密填入），此檔只保留自動模式自己的流程。

使用方式：
  第一次：python entrust_sync.py
  之後：  python entrust_sync.py --auto（需 .env）
"""

import argparse
import json
import sys
from datetime import date

from playwright.sync_api import sync_playwright

from entrust import (
    DEFAULT_TIMEOUT,
    LOGIN_URL,
    OUTPUT_DIR,
    alert_log,
    capture_aggregate_inventory,
    capture_all_tables,
    download_aggregate_inventory_xls,
    launch_browser,
)
from entrust.login import click_login_button, fill_credentials, load_credentials


def main():
    parser = argparse.ArgumentParser(description="華南永昌持股同步 v5")
    parser.add_argument("--auto", action="store_true", help="自動填入帳密")
    parser.add_argument("--debug", action="store_true", help="除錯模式")
    args = parser.parse_args()

    account, password = "", ""
    if args.auto:
        account, password = load_credentials()
        if not account or not password:
            print("❌ 需要 .env 檔案")
            sys.exit(1)
        print(f"   ✓ 帳號: {account[:3]}***")

    print("\n🏦 華南永昌持股同步 v5")
    print("=" * 40)
    print("🔑 addInitScript 攔截 alert + persistent context\n")

    with sync_playwright() as p:
        # Edge → Chromium fallback、init script、alert/popup handler
        # 全部收斂在 entrust.browser.launch_browser
        context, _ = launch_browser(p)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            print(f"🌐 開啟: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=DEFAULT_TIMEOUT)
            page.wait_for_timeout(3000)

            # 顯示 alert 紀錄
            if alert_log:
                print(f"   📋 已自動處理 {len(alert_log)} 個 alert")

            # 檢查是否已登入
            if "login" not in page.url.lower():
                print("✅ 可能已登入，跳過登入步驟")
            else:
                if args.auto and account and password:
                    print("📝 自動填入帳密...")
                    fill_credentials(page, account, password)
                    click_login_button(page)

                print("\n🔑 請在瀏覽器中完成登入")
                print("   ℹ️ 請依網頁提示輸入驗證碼；若網站要求憑證，也請依畫面完成")
                input("   👉 看到登入後的主畫面時，按 Enter 繼續...")

            page.screenshot(path=str(OUTPUT_DIR / "after_login.png"))

            # 持股
            print("\n📊 導航到「持股明細」頁面")
            input("   👉 到達後按 Enter...")
            try:
                page.screenshot(path=str(OUTPUT_DIR / "holdings.png"))
            except Exception:
                pass
            holdings = capture_all_tables(page)
            aggregate_inventory = capture_aggregate_inventory(page)
            download_aggregate_inventory_xls(page)

            # 交易
            print("\n📜 導航到「交易紀錄」頁面")
            input("   👉 到達後按 Enter...")
            try:
                page.screenshot(path=str(OUTPUT_DIR / "transactions.png"))
            except Exception:
                pass
            transactions = capture_all_tables(page)

            # 儲存
            today = date.today().isoformat()
            for name, tables in [("holdings", holdings), ("transactions", transactions)]:
                filepath = OUTPUT_DIR / f"{name}_{today}.json"
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump({"date": today, "source": "華南永昌證券",
                               "tables": tables, "alerts": alert_log}, f, ensure_ascii=False, indent=2)
                print(f"   💾 {filepath}")

            inventory_path = OUTPUT_DIR / f"aggregate_inventory_{today}.json"
            with open(inventory_path, "w", encoding="utf-8") as f:
                json.dump({"date": today, "source": "華南永昌證券",
                           "positions": aggregate_inventory}, f, ensure_ascii=False, indent=2)
            print(f"   💾 {inventory_path}（{len(aggregate_inventory)} 筆）")

            while True:
                extra = input("\n🎯 其他頁面？（名稱 / Enter 結束）: ").strip()
                if not extra:
                    break
                input(f"   導航到「{extra}」後按 Enter...")
                tables = capture_all_tables(page)
                filepath = OUTPUT_DIR / f"{extra}_{today}.json"
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump({"date": today, "tables": tables}, f, ensure_ascii=False, indent=2)

        except KeyboardInterrupt:
            print("\n⚠️ 中斷")
        except Exception as e:
            print(f"\n❌ 錯誤: {e}")
            try:
                page.screenshot(path=str(OUTPUT_DIR / "error.png"))
            except Exception:
                pass
        finally:
            context.close()
            print("\n🔒 已關閉（profile 已保存）")


if __name__ == "__main__":
    main()
