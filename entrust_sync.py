#!/usr/bin/env python3
"""
華南永昌證券 — 持股 & 交易紀錄自動同步 v2
==========================================

v2 改進：
- 處理彈出視窗（憑證申請等）
- Session 保存/載入（避免每次重新登入）
- iframe 內容抓取
- 更穩健的等待與錯誤處理
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

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
SESSION_DIR = SCRIPT_DIR / "session"
SESSION_DIR.mkdir(exist_ok=True)

LOGIN_URL = "https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx"
DEFAULT_TIMEOUT = 30_000
OTP_WAIT_TIMEOUT = 180_000  # 3 分鐘


def load_credentials() -> tuple[str, str]:
    load_dotenv(SCRIPT_DIR / ".env")
    account = os.getenv("ENTRUST_ACCOUNT", "")
    password = os.getenv("ENTRUST_PASSWORD", "")
    return account, password


def save_session(context, name: str = "default"):
    """保存瀏覽器 session"""
    state_path = SESSION_DIR / f"session_{name}.json"
    context.storage_state(path=str(state_path))
    print(f"   💾 Session 已保存: {state_path}")
    return state_path


def load_session_path() -> str | None:
    """載入已保存的 session 路徑"""
    state_path = SESSION_DIR / "session_default.json"
    if state_path.exists():
        # 檢查檔案年齡
        mtime = datetime.fromtimestamp(state_path.stat().st_mtime)
        age_hours = (datetime.now() - mtime).total_seconds() / 3600
        print(f"   📂 找到 session（{age_hours:.1f} 小時前保存）")
        if age_hours > 1:
            print("   ⚠️ Session 可能已過期（超過 1 小時）")
        return str(state_path)
    return None


def check_session_valid(page) -> bool:
    """檢查 session 是否仍然有效"""
    try:
        url = page.url.lower()
        if "login" in url:
            return False
        login_form = page.locator('input[type="password"]')
        if login_form.is_visible(timeout=3000):
            return False
        return True
    except Exception:
        return False


class PopupHandler:
    """處理華南永昌的彈出視窗"""

    def __init__(self, context, output_dir: Path):
        self.context = context
        self.output_dir = output_dir
        self.popups = []
        self.context.on("page", self._on_popup)

    def _on_popup(self, popup_page):
        print(f"   🪟 偵測到彈出視窗！")
        try:
            popup_page.wait_for_load_state("domcontentloaded", timeout=5000)
            url = popup_page.url
            title = popup_page.title()
            print(f"      URL: {url[:100]}")
            print(f"      標題: {title}")

            # 截圖
            ts = time.strftime("%H%M%S")
            screenshot_path = self.output_dir / f"popup_{ts}.png"
            popup_page.screenshot(path=str(screenshot_path))

            # 存 HTML
            try:
                content = popup_page.content()
                content_path = self.output_dir / f"popup_{ts}.html"
                with open(content_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception:
                content_path = None

            # 頁面文字
            try:
                body_text = popup_page.inner_text("body")
                if body_text and body_text.strip():
                    preview = body_text.strip()[:200]
                    print(f"      📝 內容預覽: {preview}...")
                else:
                    print("      ⚠️ 頁面文字為空")
            except Exception:
                print("      ⚠️ 無法讀取頁面文字")

            self.popups.append({
                "url": url,
                "title": title,
                "screenshot": str(screenshot_path),
                "time": ts,
            })

        except Exception as e:
            print(f"      ⚠️ 處理彈出視窗時出錯: {e}")


def capture_all_tables(page) -> list[dict]:
    """抓取頁面上所有表格（包含 iframe）"""
    tables_data = []

    # ── 主頁面表格 ──
    tables = page.locator("table").all()
    for t_idx, table in enumerate(tables):
        try:
            rows = table.locator("tr").all()
            if not rows:
                continue
            headers = []
            for cell in rows[0].locator("th, td").all():
                headers.append(cell.text_content().strip())
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
        except Exception as e:
            print(f"      ⚠️ 表格 {t_idx} 解析失敗: {e}")

    # ── iframe 表格 ──
    for i, frame in enumerate(page.frames):
        if frame == page.main_frame:
            continue
        try:
            frame_url = frame.url[:80]
            print(f"      🔍 掃描 iframe #{i}: {frame_url}")
            tables = frame.locator("table").all()
            for t_idx, table in enumerate(tables):
                try:
                    rows = table.locator("tr").all()
                    if not rows:
                        continue
                    headers = []
                    for cell in rows[0].locator("th, td").all():
                        headers.append(cell.text_content().strip())
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
        except Exception as e:
            print(f"      ⚠️ iframe #{i} 無法讀取: {e}")

    return tables_data


def save_step(step_name: str, page, tables_data: list[dict], popup_info: list = None):
    """儲存單一步驟的結果"""
    today = date.today().isoformat()
    output_file = OUTPUT_DIR / f"{step_name}_{today}.json"

    result = {
        "step": step_name,
        "date": today,
        "page_url": page.url,
        "page_title": page.title(),
        "tables": tables_data,
        "popups": popup_info or [],
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"   💾 已存: {output_file}")
    return output_file


def save_data(holdings: list[dict], transactions: list[dict]):
    """儲存最終結果"""
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

    with open(transactions_file, "w", encoding="utf-8") as f:
        json.dump({
            "date": today,
            "source": "華南永昌證券",
            "count": len(transactions),
            "transactions": transactions
        }, f, ensure_ascii=False, indent=2)

    return holdings_file, transactions_file


def main():
    parser = argparse.ArgumentParser(description="華南永昌持股同步工具 v2")
    parser.add_argument("--auto", action="store_true", help="自動模式（需設定 .env）")
    parser.add_argument("--headed", action="store_true", default=True, help="顯示瀏覽器（預設）")
    parser.add_argument("--headless", action="store_true", help="無頭模式")
    parser.add_argument("--no-session", action="store_true", help="不使用保存的 session")
    parser.add_argument("--debug", action="store_true", help="除錯模式，每步截圖")
    args = parser.parse_args()

    headed = not args.headless

    print()
    print("🏦 華南永昌持股同步工具 v2")
    print("=" * 40)
    print("v2 功能：")
    print("  ✅ 彈出視窗自動截圖記錄")
    print("  ✅ Session 保存/載入")
    print("  ✅ iframe 內容抓取")
    print()

    account, password = "", ""
    if args.auto:
        account, password = load_credentials()
        if not account or not password:
            print("❌ 自動模式需要設定 .env")
            sys.exit(1)
        print(f"   ✓ 帳號: {account[:3]}***")

    with sync_playwright() as p:
        print("🚀 啟動瀏覽器...")
        browser = p.chromium.launch(headless=not headed)

        # 載入 session
        storage_state = None
        if not args.no_session:
            storage_state = load_session_path()

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            storage_state=storage_state,
            accept_downloads=True,
        )

        popup_handler = PopupHandler(context, OUTPUT_DIR)
        page = context.new_page()

        try:
            # ── 開啟登入頁 ──
            print(f"🌐 開啟: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=DEFAULT_TIMEOUT)
            page.wait_for_timeout(2000)

            # 檢查 session
            if storage_state and check_session_valid(page):
                print("✅ Session 有效，跳過登入！")
            else:
                if args.auto and account and password:
                    # 自動填入帳密
                    print("📝 自動填入帳密...")
                    # 嘗試各種 selector
                    account_filled = False
                    password_filled = False

                    for sel in ['input[name*="id"]', 'input[name*="account"]',
                                'input[type="text"]', 'input[id*="txtID"]',
                                'input[id*="txtAccount"]', 'input[id*="Account"]']:
                        try:
                            el = page.locator(sel).first
                            if el.is_visible(timeout=2000):
                                el.click()
                                el.fill(account)
                                account_filled = True
                                print(f"   ✓ 帳號已填入")
                                break
                        except Exception:
                            continue

                    for sel in ['input[name*="pwd"]', 'input[name*="password"]',
                                'input[type="password"]', 'input[id*="txtPWD"]',
                                'input[id*="Password"]']:
                        try:
                            el = page.locator(sel).first
                            if el.is_visible(timeout=2000):
                                el.click()
                                el.fill(password)
                                password_filled = True
                                print(f"   ✓ 密碼已填入")
                                break
                        except Exception:
                            continue

                    # 點登入
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

                print()
                print("🔑 請在瀏覽器中完成登入（包含 OTP + 憑證）")
                print("   ⚠️ 如果跳出憑證視窗，請手動處理")
                print("   📸 腳本會自動截圖記錄彈出視窗")
                input("   👉 登入完成後按 Enter 繼續...")

                # 截圖確認
                page.screenshot(path=str(OUTPUT_DIR / "after_login.png"))
                print("   📸 已截圖確認登入狀態")

            if args.debug:
                page.screenshot(path=str(OUTPUT_DIR / "debug_01_after_login.png"))

            # ── 抓取持股 ──
            print()
            print("📊 請導航到「持股明細」或「庫存查詢」頁面")
            input("   👉 到達後按 Enter 抓取...")

            page.screenshot(path=str(OUTPUT_DIR / f"screenshot_holdings.png"))
            holdings_tables = capture_all_tables(page)
            save_step("holdings", page, holdings_tables, popup_handler.popups)

            if args.debug:
                page.screenshot(path=str(OUTPUT_DIR / "debug_02_holdings.png"))

            # ── 抓取交易紀錄 ──
            print()
            print("📜 請導航到「交易紀錄」或「成交查詢」頁面")
            input("   👉 到達後按 Enter 抓取...")

            page.screenshot(path=str(OUTPUT_DIR / f"screenshot_transactions.png"))
            transactions_tables = capture_all_tables(page)
            save_step("transactions", page, transactions_tables, popup_handler.popups)

            if args.debug:
                page.screenshot(path=str(OUTPUT_DIR / "debug_03_transactions.png"))

            # ── 額外頁面 ──
            while True:
                extra = input("\n🎯 要抓其他頁面嗎？（輸入名稱，或直接 Enter 結束）: ").strip()
                if not extra:
                    break
                print(f"📋 請導航到「{extra}」頁面")
                input("   👉 到達後按 Enter 抓取...")
                page.screenshot(path=str(OUTPUT_DIR / f"screenshot_{extra}.png"))
                tables = capture_all_tables(page)
                save_step(extra, page, tables, popup_handler.popups)

            # ── 保存 session ──
            if not args.no_session:
                try:
                    save_session(context)
                    print("\n💾 Session 已保存！下次啟動可以直接使用（如果未過期）")
                except Exception as e:
                    print(f"⚠️ Session 保存失敗: {e}")

            # ── 結果統計 ──
            holdings = []
            for t in holdings_tables:
                holdings.extend(t.get("data", []))

            transactions = []
            for t in transactions_tables:
                transactions.extend(t.get("data", []))

            if holdings or transactions:
                h_file, t_file = save_data(holdings, transactions)
                print()
                print("📊 同步完成！")
                print(f"   持股: {len(holdings)} 筆")
                print(f"   交易: {len(transactions)} 筆")
                print(f"\n📁 輸出：")
                print(f"   {h_file}")
                print(f"   {t_file}")
            else:
                print()
                print("⚠️ 未抓取到表格資料")
                print("   可能原因：")
                print("   1. 頁面資料在 iframe 中（腳本會自動掃描）")
                print("   2. 需要展開或切換 tab")
                print("   3. 頁面尚未載入完成")
                print("\n💡 建議用 explore.py --debug 重新執行")
                page.screenshot(path=str(OUTPUT_DIR / "debug_final.png"))

            # 彈出視窗摘要
            if popup_handler.popups:
                print(f"\n🪟 共捕獲 {len(popup_handler.popups)} 個彈出視窗")
                for p in popup_handler.popups:
                    print(f"   - {p['title']} ({p['url'][:60]})")

        except KeyboardInterrupt:
            print("\n\n⚠️ 使用者中斷")
            page.screenshot(path=str(OUTPUT_DIR / "interrupted.png"))
            if not args.no_session:
                try:
                    save_session(context)
                except Exception:
                    pass

        except Exception as e:
            print(f"\n❌ 錯誤: {e}")
            page.screenshot(path=str(OUTPUT_DIR / "error.png"))
            raise

        finally:
            context.close()
            browser.close()
            print("\n🔒 瀏覽器已關閉")


if __name__ == "__main__":
    main()