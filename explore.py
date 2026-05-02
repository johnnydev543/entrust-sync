#!/usr/bin/env python3
"""
華南永昌持股同步 — 互動探索模式 v2
===================================

v2 改進：
- 處理彈出視窗（憑證申請等 popup）
- 支援 session 保存/載入（避免每次重新登入）
- 彈出視窗會截圖保存供除錯
- 更好的等待與錯誤處理

使用方式：
  python explore.py              # 正常使用
  python explore.py --no-session # 不使用保存的 session
"""

import json
import sys
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
SESSION_DIR = SCRIPT_DIR / "session"
SESSION_DIR.mkdir(exist_ok=True)

LOGIN_URL = "https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx"


class PopupHandler:
    """處理華南永昌的彈出視窗"""

    def __init__(self, context, output_dir: Path):
        self.context = context
        self.output_dir = output_dir
        self.popups = []
        self.context.on("page", self._on_popup)

    def _on_popup(self, page):
        """當有新視窗彈出時觸發"""
        print(f"   🪟 偵測到彈出視窗！")
        try:
            # 等頁面載入
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            url = page.url
            title = page.title()
            print(f"      URL: {url}")
            print(f"      標題: {title}")

            # 截圖保存
            ts = time.strftime("%H%M%S")
            screenshot_path = self.output_dir / f"popup_{ts}.png"
            page.screenshot(path=str(screenshot_path))
            print(f"      📸 已截圖: {screenshot_path}")

            # 嘗試抓取內容
            try:
                content = page.content()
                content_path = self.output_dir / f"popup_{ts}.html"
                with open(content_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"      📄 已保存 HTML: {content_path}")

                # 分析頁面文字
                body_text = page.inner_text("body")
                if body_text and body_text.strip():
                    print(f"      📝 頁面文字: {body_text[:200]}...")
                else:
                    print("      ⚠️ 頁面文字為空（可能是空白頁或需要互動）")
            except Exception as e:
                print(f"      ⚠️ 無法取得內容: {e}")

            self.popups.append({
                "url": url,
                "title": title,
                "screenshot": str(screenshot_path),
                "time": ts,
            })

        except Exception as e:
            print(f"      ⚠️ 處理彈出視窗時出錯: {e}")


def capture_all_tables(page) -> list[dict]:
    """抓取頁面上所有表格資料"""
    tables_data = []
    tables = page.locator("table").all()

    for t_idx, table in enumerate(tables):
        try:
            rows = table.locator("tr").all()
            if not rows:
                continue

            # 偵測表頭
            headers = []
            first_row = rows[0]
            for cell in first_row.locator("th, td").all():
                headers.append(cell.text_content().strip())

            # 偵測資料行
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

            # 嘗試抓取 iframe 內的表格
            if not data_rows:
                continue

            tables_data.append({
                "table_index": t_idx,
                "headers": headers,
                "row_count": len(data_rows),
                "data": data_rows
            })
        except Exception as e:
            print(f"      ⚠️ 表格 {t_idx} 解析失敗: {e}")

    return tables_data


def capture_iframe_tables(page) -> list[dict]:
    """抓取 iframe 內的表格（華南永昌常用 iframe）"""
    all_tables = []

    # 主頁面表格
    main_tables = capture_all_tables(page)
    all_tables.extend(main_tables)

    # iframe 內表格
    frames = page.frames
    for i, frame in enumerate(frames):
        if frame == page.main_frame:
            continue
        try:
            print(f"      🔍 掃描 iframe #{i}: {frame.url[:80]}")
            frame_tables = capture_all_tables(frame)
            for t in frame_tables:
                t["source"] = f"iframe_{i}"
            all_tables.extend(frame_tables)
        except Exception as e:
            print(f"      ⚠️ iframe #{i} 無法讀取: {e}")

    return all_tables


def capture_all_tables(context_or_page) -> list[dict]:
    """抓取頁面上所有表格資料（包含 iframe）"""
    # 如果是 page，先抓主頁面
    tables_data = []

    if hasattr(context_or_page, "frames"):
        # 這是 page 物件
        page = context_or_page

        # 主頁面表格
        tables = page.locator("table").all()
        for t_idx, table in enumerate(tables):
            try:
                rows = table.locator("tr").all()
                if not rows:
                    continue

                headers = []
                first_row = rows[0]
                for cell in first_row.locator("th, td").all():
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

        # iframe 表格
        for i, frame in enumerate(page.frames):
            if frame == page.main_frame:
                continue
            try:
                print(f"      🔍 掃描 iframe #{i}: {frame.url[:80]}")
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


def save_session(context, name: str = "default"):
    """保存瀏覽器 session（cookies, localStorage 等）"""
    state_path = SESSION_DIR / f"session_{name}.json"
    context.storage_state(path=str(state_path))
    print(f"   💾 Session 已保存: {state_path}")
    return state_path


def load_session() -> str | None:
    """載入已保存的 session"""
    state_path = SESSION_DIR / "session_default.json"
    if state_path.exists():
        print(f"   📂 找到已保存的 session: {state_path}")
        return str(state_path)
    return None


def check_session_valid(page) -> bool:
    """檢查 session 是否仍然有效（未過期）"""
    try:
        # 如果還在登入頁，代表 session 已過期
        current_url = page.url
        if "login" in current_url.lower():
            return False
        # 如果頁面有登入表單，也代表過期
        login_form = page.locator('input[type="password"]')
        if login_form.is_visible(timeout=3000):
            return False
        return True
    except Exception:
        return False


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


def main():
    import argparse
    parser = argparse.ArgumentParser(description="華南永昌持股同步 — 探索模式 v2")
    parser.add_argument("--no-session", action="store_true", help="不使用保存的 session")
    args = parser.parse_args()

    print()
    print("🏦 華南永昌持股同步 — 探索模式 v2")
    print("=" * 45)
    print()
    print("v2 改進：")
    print("  ✅ 自動處理彈出視窗（截圖 + 存 HTML）")
    print("  ✅ 支援 session 保存/載入")
    print("  ✅ 支援 iframe 內容抓取")
    print("  ✅ 每步截圖除錯")
    print()
    print("流程：")
    print("  1. 腳本開啟瀏覽器（如有 session 會自動載入）")
    print("  2. 手動登入 + 處理憑證視窗")
    print("  3. 手動導航到想抓的頁面，按 Enter 抓取")
    print("  4. 可以重複抓取多個頁面")
    print("  5. 結束時自動保存 session")
    print()

    steps = [
        ("login", "請在瀏覽器中完成登入（帳密 + OTP + 憑證）"),
        ("holdings", "請導航到「持股明細」或「庫存查詢」頁面"),
        ("transactions", "請導航到「交易紀錄」或「成交查詢」頁面"),
    ]

    with sync_playwright() as p:
        print("🚀 啟動瀏覽器...")
        browser = p.chromium.launch(headless=False)

        # 嘗試載入已保存的 session
        storage_state = None
        if not args.no_session:
            storage_state = load_session()

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            storage_state=storage_state,
            accept_downloads=True,
        )

        # 設定彈出視窗處理
        popup_handler = PopupHandler(context, OUTPUT_DIR)

        page = context.new_page()

        try:
            # ── 開啟登入頁 ──
            print(f"🌐 開啟: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # 檢查 session 是否有效
            if storage_state and check_session_valid(page):
                print("✅ Session 仍然有效，不需要重新登入！")
            else:
                if storage_state:
                    print("⚠️ Session 已過期，需要重新登入")
                print("📋 請在瀏覽器中完成登入")
                print("   ⚠️ 如果跳出憑證視窗，請手動處理")
                print("   📸 腳本會自動截圖記錄彈出視窗")

            # ── 互動步驟 ──
            all_results = {}

            for step_name, prompt in steps:
                print()
                print(f"📋 {prompt}")
                input("   👉 完成後按 Enter 繼續...")

                # 截圖
                page.screenshot(path=str(OUTPUT_DIR / f"screenshot_{step_name}.png"))
                print("   📸 已截圖")

                # 抓取表格（含 iframe）
                tables = capture_all_tables(page)
                if tables:
                    print(f"   📊 找到 {len(tables)} 個表格")
                    for t in tables:
                        src = t.get('source', 'main')
                        print(f"      [{src}] 表格 {t['table_index']}: "
                              f"{t['row_count']} 行, "
                              f"欄位: {', '.join(t['headers'][:6])}"
                              f"{'...' if len(t['headers']) > 6 else ''}")
                else:
                    print("   ⚠️ 沒找到表格")
                    print("   💡 可能需要：")
                    print("      - 展開折疊的區塊")
                    print("      - 切換 tab 或 iframe")
                    print("      - 等資料載入完成再按 Enter")

                # 儲存
                save_step(step_name, page, tables, popup_handler.popups)
                all_results[step_name] = {
                    "url": page.url,
                    "title": page.title(),
                    "tables_count": len(tables),
                    "popups": len(popup_handler.popups),
                }

            # 額外頁面
            while True:
                print()
                extra = input("🎯 要抓其他頁面嗎？（輸入名稱，或直接 Enter 結束）: ").strip()
                if not extra:
                    break

                print(f"📋 請導航到「{extra}」頁面")
                input("   👉 完成後按 Enter 繼續...")

                page.screenshot(path=str(OUTPUT_DIR / f"screenshot_{extra}.png"))
                tables = capture_all_tables(page)
                save_step(extra, page, tables, popup_handler.popups)
                all_results[extra] = {
                    "url": page.url,
                    "title": page.title(),
                    "tables_count": len(tables),
                }

            # ── 保存 session ──
            if not args.no_session:
                try:
                    save_session(context)
                    print()
                    print("💾 Session 已保存！下次啟動可以直接使用（如果未過期）")
                except Exception as e:
                    print(f"⚠️ Session 保存失敗: {e}")

            # ── 總結 ──
            summary_file = OUTPUT_DIR / f"full_sync_{date.today().isoformat()}.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump({
                    "date": date.today().isoformat(),
                    "source": "華南永昌證券",
                    "login_url": LOGIN_URL,
                    "steps": all_results,
                    "popups_captured": len(popup_handler.popups),
                }, f, ensure_ascii=False, indent=2)

            print()
            print("📊 同步完成！")
            print(f"📁 完整結果: {summary_file}")
            print()
            print("📂 輸出檔案：")
            for f in sorted(OUTPUT_DIR.glob("*")):
                if f.is_file():
                    size = f.stat().st_size
                    print(f"   {f.name} ({size:,} bytes)")

            # 顯示彈出視窗資訊
            if popup_handler.popups:
                print()
                print(f"🪟 共捕獲 {len(popup_handler.popups)} 個彈出視窗：")
                for p in popup_handler.popups:
                    print(f"   URL: {p['url']}")
                    print(f"   標題: {p['title']}")
                    print(f"   截圖: {p['screenshot']}")

        except KeyboardInterrupt:
            print("\n\n⚠️ 使用者中斷")
            page.screenshot(path=str(OUTPUT_DIR / "interrupted.png"))
            # 嘗試保存 session
            if not args.no_session:
                try:
                    save_session(context)
                except Exception:
                    pass

        except Exception as e:
            print(f"\n❌ 錯誤: {e}")
            try:
                page.screenshot(path=str(OUTPUT_DIR / "error.png"))
            except Exception:
                pass

        finally:
            context.close()
            browser.close()
            print("\n🔒 瀏覽器已關閉")


if __name__ == "__main__":
    main()