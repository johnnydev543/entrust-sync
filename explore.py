#!/usr/bin/env python3
"""
華南永昌持股同步 — 探索模式 v4
===================================

v4 改進：
- 自動處理 JavaScript alert（錯誤 5010、憑證提示等）
- 憑證 popup window：嘗試攔截並截圖分析
- persistent context：憑證只需安裝一次

Alert 流程：
  1. Alert: 錯誤代碼 5010 → 自動按 OK
  2. Alert: 您尚未下載憑證 → 自動按 OK
  3. Popup window（無 URL）→ 截圖 + 存 HTML 供分析
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
USER_DATA_DIR = SCRIPT_DIR / "browser_profile"

LOGIN_URL = "https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx"


# ─── Alert 記錄 ──────────────────────────────────────────────
alert_log = []


def on_dialog(dialog):
    """自動處理 JavaScript alert/confirm/prompt"""
    msg = dialog.message
    print(f"   💬 [Alert] {dialog.type}: {msg[:200]}")
    alert_log.append({
        "type": dialog.type,
        "message": msg,
        "time": time.strftime("%H:%M:%S"),
    })
    # 全部自動按 OK / 確定
    dialog.accept()


def on_page_created(new_page):
    """攔截新開的視窗"""
    print(f"   🪟 [Popup] 新視窗開啟！")
    try:
        new_page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass

    url = ""
    title = ""
    try:
        url = new_page.url
        title = new_page.title()
    except Exception:
        pass

    print(f"      URL: {url or '(空白)'}")
    print(f"      標題: {title or '(空白)'}")

    # 截圖
    ts = time.strftime("%H%M%S")
    try:
        new_page.screenshot(path=str(OUTPUT_DIR / f"popup_{ts}.png"))
        print(f"      📸 截圖: popup_{ts}.png")
    except Exception as e:
        print(f"      ⚠️ 截圖失敗: {e}")

    # 嘗試讀取內容
    try:
        html = new_page.content()
        html_path = OUTPUT_DIR / f"popup_{ts}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"      📄 HTML 已存: popup_{ts}.html")

        # 讀取頁面文字
        try:
            text = new_page.inner_text("body")
            if text and text.strip():
                print(f"      📝 文字內容: {text.strip()[:300]}")
            else:
                print(f"      ⚠️ 頁面文字為空")
                # 嘗試讀取所有 input
                inputs = new_page.locator("input, select, button").all()
                if inputs:
                    print(f"      🔍 找到 {len(inputs)} 個表單元素：")
                    for inp in inputs[:10]:
                        try:
                            tag = inp.evaluate("el => el.outerHTML.substring(0, 200)")
                            print(f"         {tag}")
                        except Exception:
                            pass
        except Exception as e:
            print(f"      ⚠️ 無法讀取文字: {e}")

    except Exception as e:
        print(f"      ⚠️ 無法讀取內容: {e}")

    # 檢查是否有 iframe
    try:
        frames = new_page.frames
        if len(frames) > 1:
            print(f"      🖼️ 找到 {len(frames) - 1} 個 iframe：")
            for i, frame in enumerate(frames):
                if frame != new_page.main_frame:
                    print(f"         iframe #{i}: {frame.url[:100]}")
    except Exception:
        pass


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
        "alerts": alert_log.copy(),
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"   💾 已存: {output_file}")
    return output_file


def main():
    global alert_log

    print()
    print("🏦 華南永昌持股同步 — 探索模式 v4")
    print("=" * 45)
    print()
    print("🔑 v4 改進：")
    print("   ✅ 自動處理 alert（5010 錯誤、憑證提示）")
    print("   ✅ 攔截並分析 popup window")
    print("   ✅ persistent context（憑證只需裝一次）")
    print()
    print("⚠️ 憑證 popup 如果沒有 URL：")
    print("   → 腳本會截圖存 HTML")
    print("   → 如果是 Windows 元件，需要手動操作")
    print("   → 操作完後回到終端按 Enter 即可")
    print()

    steps = [
        ("login", "請在瀏覽器中完成登入（帳密 + OTP + 憑證）"),
        ("holdings", "請導航到「持股明細」或「庫存查詢」頁面"),
        ("transactions", "請導航到「交易紀錄」或「成交查詢」頁面"),
    ]

    with sync_playwright() as p:
        print("🚀 啟動瀏覽器（persistent context）...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
        )

        # ── 註冊事件處理器 ──
        context.on("page", on_page_created)

        page = context.pages[0] if context.pages else context.new_page()
        page.on("dialog", on_dialog)  # 自動處理 alert

        # 也對所有新頁面註冊 dialog handler
        # (context.on("page") 已經在 on_page_created 處理)

        try:
            print(f"\n🌐 開啟: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            print(f"   頁面: {page.url[:80]}")
            print(f"   標題: {page.title()}")

            # 如果有 alert 自動跳出，dialog handler 會自動按 OK
            # 等一下讓 alert 處理完畢
            page.wait_for_timeout(2000)

            if alert_log:
                print(f"\n   📋 已自動處理 {len(alert_log)} 個 alert：")
                for a in alert_log:
                    print(f"      [{a['type']}] {a['message'][:100]}")

            all_results = {}

            for step_name, prompt in steps:
                alert_log.clear()  # 清除上一步的 alert 紀錄

                print(f"\n📋 {prompt}")
                print("   💡 alert 會自動按 OK，憑證 popup 需手動處理")
                input("   👉 完成後按 Enter 繼續...")

                # 截圖
                page.screenshot(path=str(OUTPUT_DIR / f"screenshot_{step_name}.png"))

                # 如果有新開的 popup，也截圖所有頁面
                all_pages = context.pages
                if len(all_pages) > 1:
                    print(f"   📄 目前有 {len(all_pages)} 個瀏覽器視窗")
                    for i, pg in enumerate(all_pages):
                        try:
                            pg.screenshot(path=str(OUTPUT_DIR / f"screenshot_{step_name}_page{i}.png"))
                            print(f"      Page {i}: {pg.url[:80]} → 截圖已存")
                        except Exception as e:
                            print(f"      Page {i}: 截圖失敗 ({e})")

                # 抓取主頁面表格
                tables = capture_all_tables(page)

                # 也嘗試從其他頁面抓取
                for i, pg in enumerate(all_pages):
                    if pg == page:
                        continue
                    try:
                        extra_tables = capture_all_tables(pg)
                        if extra_tables:
                            for t in extra_tables:
                                t["source"] = f"page_{i}"
                            tables.extend(extra_tables)
                            print(f"   📊 從 page_{i} 抓到 {len(extra_tables)} 個表格")
                    except Exception:
                        pass

                if tables:
                    print(f"   📊 共找到 {len(tables)} 個表格")
                    for t in tables:
                        src = t.get('source', 'main')
                        print(f"      [{src}] {t['row_count']} 行, "
                              f"欄位: {', '.join(t['headers'][:6])}"
                              f"{'...' if len(t['headers']) > 6 else ''}")
                else:
                    print("   ⚠️ 沒找到表格")
                    print("   💡 可能需要：展開區塊 / 切換 tab / 等資料載入")

                # 顯示這步的 alert 紀錄
                if alert_log:
                    print(f"   📋 這步出現了 {len(alert_log)} 個 alert：")
                    for a in alert_log:
                        print(f"      [{a['type']}] {a['message'][:150]}")

                save_step(step_name, page, tables)
                all_results[step_name] = {
                    "url": page.url,
                    "title": page.title(),
                    "tables_count": len(tables),
                    "alerts": alert_log.copy(),
                }

            # 額外頁面
            while True:
                extra = input("\n🎯 其他頁面？（名稱 / Enter 結束）: ").strip()
                if not extra:
                    break
                input(f"   導航到「{extra}」後按 Enter...")
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
                    "total_alerts": sum(len(r.get("alerts", [])) for r in all_results.values()),
                }, f, ensure_ascii=False, indent=2)

            print(f"\n📊 同步完成！結果: {summary_file}")
            print(f"   📂 所有截圖和 HTML 在: {OUTPUT_DIR}")

        except KeyboardInterrupt:
            print("\n\n⚠️ 使用者中斷")
            page.screenshot(path=str(OUTPUT_DIR / "interrupted.png"))

        except Exception as e:
            print(f"\n❌ 錯誤: {e}")
            page.screenshot(path=str(OUTPUT_DIR / "error.png"))

        finally:
            context.close()
            print("\n🔒 瀏覽器已關閉（profile 已保存）")
            print(f"   Profile: {USER_DATA_DIR}")


if __name__ == "__main__":
    main()