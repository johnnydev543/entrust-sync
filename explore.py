#!/usr/bin/env python3
"""
華南永昌持股同步 — 探索模式 v3
===================================

v3 核心改動：
- 使用 persistent context（持續性瀏覽器設定檔）
  → 憑證只需安裝一次，之後自動帶著
- 不再攔截彈出視窗（那是 Windows 元件，抓不到）
- 改用「你操作，腳本等你」的模式

使用方式：
  第一次：python explore.py
    → 在瀏覽器中完成登入 + 憑證申請
    → 關閉後，憑證保存在瀏覽器 profile 中
  
  之後：python explore.py
    → 自動載入 profile（含憑證）
    → 只需輸入帳密 + OTP
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
# 用 persistent context — 瀏覽器資料存在這裡（含憑證、cookies）
USER_DATA_DIR = SCRIPT_DIR / "browser_profile"

LOGIN_URL = "https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx"


def capture_all_tables(page) -> list[dict]:
    """抓取頁面上所有表格（含 iframe）"""
    tables_data = []

    # 主頁面
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
        except Exception as e:
            print(f"      ⚠️ 表格 {t_idx} 解析失敗: {e}")

    # iframe
    for i, frame in enumerate(page.frames):
        if frame == page.main_frame:
            continue
        try:
            print(f"      🔍 iframe #{i}: {frame.url[:80]}")
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
        except Exception as e:
            print(f"      ⚠️ iframe #{i}: {e}")

    return tables_data


def save_step(step_name: str, page, tables_data: list[dict]):
    """儲存單一步驟"""
    today = date.today().isoformat()
    output_file = OUTPUT_DIR / f"{step_name}_{today}.json"

    result = {
        "step": step_name,
        "date": today,
        "page_url": page.url,
        "page_title": page.title(),
        "tables": tables_data,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"   💾 已存: {output_file}")
    return output_file


def main():
    print()
    print("🏦 華南永昌持股同步 — 探索模式 v3")
    print("=" * 45)
    print()
    print("🔑 persistent context 模式：")
    print("   → 瀏覽器資料（憑證、cookies）會保存在 browser_profile/")
    print("   → 第一次需要手動處理憑證")
    print("   → 之後憑證會跟著 profile，不用再處理")
    print()
    print("操作方式：")
    print("   1. 瀏覽器開啟後，手動完成登入（帳密 + OTP）")
    print("   2. 如有憑證視窗，手動處理（只會出現一次）")
    print("   3. 登入完成後回到終端按 Enter")
    print("   4. 導航到想抓的頁面，按 Enter 抓取")
    print()

    steps = [
        ("login", "請在瀏覽器中完成登入（帳密 + OTP + 憑證）"),
        ("holdings", "請導航到「持股明細」或「庫存查詢」頁面"),
        ("transactions", "請導航到「交易紀錄」或「成交查詢」頁面"),
    ]

    with sync_playwright() as p:
        print("🚀 啟動瀏覽器（persistent context）...")
        print(f"   Profile: {USER_DATA_DIR}")

        # 用 persistent context — 關鍵差異！
        # 這樣憑證和 cookies 都會保存在 browser_profile/ 目錄中
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
        )

        # 取得第一個頁面（或建立新的）
        if len(context.pages) > 0:
            page = context.pages[0]
        else:
            page = context.new_page()

        try:
            print(f"\n🌐 開啟: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # 顯示頁面狀態
            print(f"   頁面: {page.url[:80]}")
            print(f"   標題: {page.title()}")

            all_results = {}

            for step_name, prompt in steps:
                print(f"\n📋 {prompt}")
                input("   👉 完成後按 Enter 繼續...")

                # 截圖
                page.screenshot(path=str(OUTPUT_DIR / f"screenshot_{step_name}.png"))
                print("   📸 已截圖")

                # 抓取
                tables = capture_all_tables(page)
                if tables:
                    print(f"   📊 找到 {len(tables)} 個表格")
                    for t in tables:
                        src = t.get('source', 'main')
                        print(f"      [{src}] {t['row_count']} 行, "
                              f"欄位: {', '.join(t['headers'][:6])}"
                              f"{'...' if len(t['headers']) > 6 else ''}")
                else:
                    print("   ⚠️ 沒找到表格")
                    print("   💡 可能需要展開區塊或切換 tab")

                save_step(step_name, page, tables)
                all_results[step_name] = {
                    "url": page.url,
                    "title": page.title(),
                    "tables_count": len(tables),
                }

            # 額外頁面
            while True:
                extra = input("\n🎯 要抓其他頁面嗎？（輸入名稱，或直接 Enter 結束）: ").strip()
                if not extra:
                    break
                print(f"📋 請導航到「{extra}」頁面")
                input("   👉 完成後按 Enter...")
                page.screenshot(path=str(OUTPUT_DIR / f"screenshot_{extra}.png"))
                tables = capture_all_tables(page)
                save_step(extra, page, tables)

            # 總結
            summary_file = OUTPUT_DIR / f"full_sync_{date.today().isoformat()}.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump({
                    "date": date.today().isoformat(),
                    "source": "華南永昌證券",
                    "steps": all_results,
                }, f, ensure_ascii=False, indent=2)

            print(f"\n📊 同步完成！結果: {summary_file}")

        except KeyboardInterrupt:
            print("\n\n⚠️ 使用者中斷")
            page.screenshot(path=str(OUTPUT_DIR / "interrupted.png"))

        except Exception as e:
            print(f"\n❌ 錯誤: {e}")
            page.screenshot(path=str(OUTPUT_DIR / "error.png"))

        finally:
            # persistent context 關閉時會自動保存 profile
            context.close()
            print("🔒 瀏覽器已關閉（profile 已保存）")
            print(f"   下次啟動會自動載入: {USER_DATA_DIR}")


if __name__ == "__main__":
    main()