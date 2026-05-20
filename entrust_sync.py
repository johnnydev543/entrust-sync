#!/usr/bin/env python3
"""
華南永昌持股同步 — 自動模式 v4
=================================

v4: 自動處理 alert、persistent context、popup 分析

使用方式：
  第一次：python entrust_sync.py
  之後：  python entrust_sync.py --auto（需 .env）
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
USER_DATA_DIR = SCRIPT_DIR / "browser_profile"

LOGIN_URL = "https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx"
DEFAULT_TIMEOUT = 30_000

alert_log = []


def on_dialog(dialog):
    """自動處理 JavaScript alert"""
    msg = dialog.message
    print(f"   💬 [Alert] {dialog.type}: {msg[:200]}")
    alert_log.append({"type": dialog.type, "message": msg})
    try:
        dialog.accept()
    except Exception:
        pass


def on_popup(new_page):
    """攔截彈出視窗，立即關閉不需要的 popup"""
    print(f"   🪟 [Popup] 新視窗！")

    # 記錄初始 URL
    try:
        initial_url = new_page.url
        print(f"      初始 URL: {initial_url or '(空白)'}")
    except Exception:
        initial_url = ""

    # 立即判斷是否需要關閉 — 不等待載入，避免觸發 dialog 導致 debugger paused
    should_close = False
    close_reason = ""

    if "TransPage" in (initial_url or ""):
        should_close = True
        close_reason = "TransPage.aspx"
    elif "ElectricCA" in (initial_url or "") or "CertCaApply" in (initial_url or ""):
        should_close = True
        close_reason = "憑證申請頁面"
    elif not initial_url or initial_url.lower() == "about:blank":
        # about:blank — 稍後再判斷
        pass

    if should_close:
        print(f"      🔄 立即關閉 popup: {close_reason}")
        try:
            new_page.close()
        except Exception:
            pass
        return

    # 對於不確定的頁面，等待一小段時間
    try:
        new_page.wait_for_load_state("domcontentloaded", timeout=3000)
    except Exception:
        pass

    url = ""
    title = ""
    try:
        url = new_page.url
        title = new_page.title()
    except Exception:
        print(f"      ⚠️ 頁面已關閉")
        return

    print(f"      URL: {url or '(空白)'}")
    print(f"      標題: {title or '(空白)'}")

    # 再次判斷
    if "TransPage" in (url or ""):
        print(f"      🔄 關閉 popup: TransPage.aspx")
        try:
            new_page.close()
        except Exception:
            pass
        return
    elif "ElectricCA" in (url or "") or "CertCaApply" in (url or ""):
        print(f"      🔄 關閉 popup: 憑證申請頁面")
        try:
            new_page.close()
        except Exception:
            pass
        return
    elif not url or url.lower() == "about:blank":
        print(f"      🔄 關閉空白頁面")
        try:
            new_page.close()
        except Exception:
            pass
        return

    # 保留有意義的頁面
    ts = time.strftime("%H%M%S")
    try:
        new_page.screenshot(path=str(OUTPUT_DIR / f"popup_{ts}.png"))
        print(f"      📸 截圖: popup_{ts}.png")
    except Exception as e:
        print(f"      ⚠️ 截圖失敗: {e}")
    try:
        html = new_page.content()
        with open(OUTPUT_DIR / f"popup_{ts}.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"      📄 HTML 已存 ({len(html)} chars)")
    except Exception as e:
        print(f"      ⚠️ 無法讀取內容: {e}")


def load_credentials() -> tuple[str, str]:
    load_dotenv(SCRIPT_DIR / ".env")
    return os.getenv("ENTRUST_ACCOUNT", ""), os.getenv("ENTRUST_PASSWORD", "")


def capture_all_tables(page) -> list[dict]:
    """抓取所有表格（含 iframe 和其他頁面）"""
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
                "table_index": t_idx, "headers": headers,
                "row_count": len(data_rows), "data": data_rows, "source": "main",
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
                        "table_index": t_idx, "headers": headers,
                        "row_count": len(data_rows), "data": data_rows,
                        "source": f"iframe_{i}",
                    })
                except Exception:
                    pass
        except Exception:
            pass

    return tables_data


def main():
    global alert_log

    parser = argparse.ArgumentParser(description="華南永昌持股同步 v4")
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

    print("\n🏦 華南永昌持股同步 v4")
    print("=" * 40)
    print("🔑 persistent context + alert 自動處理\n")

    with sync_playwright() as p:
        # 嘗試使用 Edge（支援 ActiveX/COM 憑證元件），若無則退回 Chromium
        browser_channel = "msedge"
        launch_args = [
            "--disable-popup-blocking",
            "--disable-features=PopupBlocker",
        ]
        try:
            print("🚀 啟動瀏覽器（嘗試 Edge）...")
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(USER_DATA_DIR),
                channel=browser_channel,
                headless=False,
                viewport={"width": 1920, "height": 1080},
                accept_downloads=True,
                args=launch_args,
            )
        except Exception as e:
            print(f"⚠️ Edge 啟動失敗（{e}），改用 Chromium...")
            browser_channel = "chromium"
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(USER_DATA_DIR),
                headless=False,
                viewport={"width": 1920, "height": 1080},
                accept_downloads=True,
                args=launch_args,
            )
        print(f"   ✅ 使用瀏覽器: {browser_channel}")

        context.on("page", on_popup)
        # 用 context.on("dialog") 處理所有頁面（含 iframe）的 alert
        context.on("dialog", on_dialog)

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
                    for sel in ['button:has-text("登入")', 'input[type="submit"]',
                                'a:has-text("登入")', '#btnLogin']:
                        try:
                            btn = page.locator(sel).first
                            if btn.is_visible(timeout=2000):
                                btn.click(); print("   ✓ 登入"); break
                        except Exception:
                            continue

                print("\n🔑 請完成登入（OTP + 憑證）")
                print("   💡 alert 會自動按 OK")
                print("   💡 憑證 popup 請手動處理")
                input("   👉 完成後按 Enter...")

            page.screenshot(path=str(OUTPUT_DIR / "after_login.png"))

            # 持股
            print("\n📊 導航到「持股明細」頁面")
            input("   👉 到達後按 Enter...")
            try:
                page.screenshot(path=str(OUTPUT_DIR / "holdings.png"))
            except Exception:
                pass
            holdings = capture_all_tables(page)

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