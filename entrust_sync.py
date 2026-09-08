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
import re
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
    """以非阻塞方式記錄彈出視窗，不干預網站的登入與憑證流程。"""
    print(f"   🪟 [Popup] 新視窗！")

    try:
        initial_url = new_page.url
        print(f"      初始 URL: {initial_url or '(空白)'}")
    except Exception:
        return

    # page 事件發生時通常仍是 about:blank。只監聽後續導航，不能在事件
    # callback 中等待或關閉視窗，否則可能打斷網站的 session 轉接。
    def log_navigation(frame):
        if frame == new_page.main_frame:
            print(f"      導航至: {frame.url or '(空白)'}")

    new_page.on("framenavigated", log_navigation)


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


def capture_aggregate_inventory(page) -> list[dict]:
    """擷取「證券彙總庫存查詢」的 25 欄明細，轉成穩定欄位。"""
    positions = {}
    groups = [
        ("depository", 1),
        ("odd_lot", 7),
        ("margin", 13),
        ("short", 19),
    ]
    fields = ["previous", "buy_order", "buy_filled", "sell_order", "sell_filled", "current"]

    def number(value):
        value = value.strip().replace(",", "")
        try:
            return int(value) if value else 0
        except ValueError:
            return value

    for frame in page.frames:
        try:
            for table in frame.locator("table").all():
                for row in table.locator("tr").all():
                    cells = row.locator(":scope > td").all()
                    if len(cells) != 25:
                        continue
                    values = [(cell.inner_text() or "").strip() for cell in cells]
                    match = re.search(r"\(([^()]+)\)\s*$", values[0])
                    if not match:
                        continue
                    code = match.group(1)
                    name = re.sub(r"^\*|\*?\([^()]+\)\s*$", "", values[0]).strip("*")
                    item = {"code": code, "name": name}
                    for group, start in groups:
                        item[group] = {
                            field: number(values[start + offset])
                            for offset, field in enumerate(fields)
                        }
                    positions[code] = item
        except Exception:
            pass

    return list(positions.values())


def download_aggregate_inventory_xls(page):
    """點擊彙總庫存匯出按鈕，將站方 XLS 永久保存到 output。"""
    for frame in page.frames:
        if "TS0106.aspx" not in frame.url:
            continue
        for selector in [
            'input[type="image"][src*="export" i]',
            'img[src*="export" i]',
        ]:
            try:
                button = frame.locator(selector).first
                if not button.is_visible(timeout=1000):
                    continue
                with page.expect_download(timeout=DEFAULT_TIMEOUT) as download_info:
                    button.click()
                download = download_info.value
                suffix = Path(download.suggested_filename).suffix or ".xls"
                filepath = OUTPUT_DIR / f"aggregate_inventory_{date.today().isoformat()}{suffix}"
                download.save_as(str(filepath))
                print(f"   📥 庫存 XLS 已存: {filepath}")
                return filepath
            except Exception:
                continue
    print("   ⚠️ 找不到庫存 XLS 匯出按鈕，或下載未開始")
    return None


def main():
    global alert_log

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
        # 嘗試使用 Edge（支援 ActiveX/COM 憑證元件），若無則退回 Chromium
        browser_channel = "msedge"
        launch_args = [
            "--disable-popup-blocking",
            "--disable-features=PopupBlocker",
            "--disable-blink-features=AutomationControlled",
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

        # ── 注入 addInitScript：在每個頁面載入前覆蓋 alert/confirm ──
        context.add_init_script("""
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
        """)
        print("   ✅ addInitScript 已注入（alert/confirm/window.open 覆蓋）")

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
