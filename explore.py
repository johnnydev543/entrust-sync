#!/usr/bin/env python3
"""
華南永昌持股同步 — 互動探索模式
===================================

這個版本會開啟瀏覽器讓你手動操作，
但會記錄你操作的頁面結構，方便後續自動化。

使用方式：
  python explore.py

流程：
  1. 自動開啟華南永昌登入頁
  2. 你手動登入（輸入帳密 + OTP）
  3. 登入後，在終端按 Enter
  4. 腳本會記錄目前頁面的所有表格資料
  5. 你手動導航到「持股明細」頁面
  6. 按 Enter，腳本抓取持股資料
  7. 你導航到「交易紀錄」頁面
  8. 按 Enter，腳本抓取交易紀錄
  9. 全部存成 JSON

這是第一步：先探索頁面結構，之後再寫全自動版本。
"""

import json
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

LOGIN_URL = "https://wm.entrust.com.tw/ftr_hns_wm/WebLogin.aspx"


def capture_all_tables(page) -> list[dict]:
    """抓取頁面上所有表格資料"""
    tables_data = []
    tables = page.locator("table").all()

    for t_idx, table in enumerate(tables):
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

        tables_data.append({
            "table_index": t_idx,
            "headers": headers,
            "row_count": len(data_rows),
            "data": data_rows
        })

    return tables_data


def capture_page_info(page) -> dict:
    """記錄頁面基本資訊"""
    return {
        "url": page.url,
        "title": page.title(),
    }


def save_step(step_name: str, page, tables_data: list[dict]):
    """儲存單一步驟的結果"""
    today = date.today().isoformat()
    output_file = OUTPUT_DIR / f"{step_name}_{today}.json"

    info = capture_page_info(page)

    result = {
        "step": step_name,
        "date": today,
        "page_info": info,
        "tables": tables_data,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"   💾 已存: {output_file}")
    return output_file


def main():
    print()
    print("🏦 華南永昌持股同步 — 探索模式")
    print("=" * 45)
    print()
    print("這個腳本會幫你：")
    print("  1. 開啟瀏覽器到華南永昌登入頁")
    print("  2. 你手動登入（帳密 + OTP）")
    print("  3. 你手動導航到想抓的頁面")
    print("  4. 按 Enter，腳本抓取所有表格資料")
    print()
    print("按 Ctrl+C 隨時結束")
    print()

    steps = [
        ("login", "請在瀏覽器中完成登入（帳密 + OTP）"),
        ("holdings", "請導航到「持股明細」或「庫存查詢」頁面"),
        ("transactions", "請導航到「交易紀錄」或「成交查詢」頁面"),
    ]

    with sync_playwright() as p:
        print("🚀 啟動瀏覽器...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print(f"🌐 開啟登入頁: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="networkidle")
            print()

            all_results = {}

            for step_name, prompt in steps:
                print(f"📋 {prompt}")
                input("   按 Enter 繼續...")

                # 截圖
                page.screenshot(path=str(OUTPUT_DIR / f"screenshot_{step_name}.png"))
                print("   📸 已截圖")

                # 抓取表格
                tables = capture_all_tables(page)
                if tables:
                    print(f"   📊 找到 {len(tables)} 個表格")
                    for t in tables:
                        print(f"      表格 {t['table_index']}: {t['row_count']} 行, "
                              f"欄位: {', '.join(t['headers'][:5])}{'...' if len(t['headers']) > 5 else ''}")
                else:
                    print("   ⚠️ 沒找到表格，可能需要展開或切換 tab")

                # 儲存
                save_step(step_name, page, tables)
                all_results[step_name] = {
                    "tables": tables,
                    "url": page.url,
                    "title": page.title(),
                }
                print()

            # 再問一次：要不要繼續抓其他頁面？
            while True:
                print("✅ 主要步驟完成！")
                extra = input("   要抓其他頁面嗎？（輸入名稱，或直接 Enter 結束）: ").strip()
                if not extra:
                    break
                print(f"📋 請導航到「{extra}」頁面")
                input("   按 Enter 繼續...")
                page.screenshot(path=str(OUTPUT_DIR / f"screenshot_{extra}.png"))
                tables = capture_all_tables(page)
                save_step(extra, page, tables)
                print()

            # 儲存總結
            summary_file = OUTPUT_DIR / f"full_sync_{date.today().isoformat()}.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump({
                    "date": date.today().isoformat(),
                    "source": "華南永昌證券",
                    "steps": {k: {"url": v["url"], "tables_count": len(v["tables"])}
                              for k, v in all_results.items()},
                    "data": all_results,
                }, f, ensure_ascii=False, indent=2)

            print(f"📁 完整同步結果: {summary_file}")

        except KeyboardInterrupt:
            print("\n\n⚠️ 使用者中斷")
            page.screenshot(path=str(OUTPUT_DIR / "interrupted.png"))

        except Exception as e:
            print(f"\n❌ 錯誤: {e}")
            page.screenshot(path=str(OUTPUT_DIR / "error.png"))

        finally:
            context.close()
            browser.close()
            print("🔒 瀏覽器已關閉")


if __name__ == "__main__":
    main()