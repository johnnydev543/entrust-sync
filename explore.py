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
    # 必須用 dialog.accept()，否則瀏覽器會暫停等待使用者回應
    try:
        dialog.accept()
    except Exception:
        # 如果 dialog 已經被關閉（例如使用者手動按了），忽略錯誤
        pass


def on_page_created(new_page):
    """攔截新開的視窗，立即關閉不需要的 popup"""
    print(f"   🪟 [Popup] 新視窗開啟！")

    # 記錄初始 URL
    try:
        initial_url = new_page.url
        print(f"      初始 URL: {initial_url or '(空白)'}")
    except Exception:
        initial_url = ""

    # 判斷是否需要關閉 — 基於初始 URL 立即判斷，不等待載入
    # 這是關鍵：等待載入會觸發 dialog，導致 "debugger paused"
    should_close = False
    close_reason = ""

    if "TransPage" in (initial_url or ""):
        should_close = True
        close_reason = "TransPage.aspx（交易過渡頁）"
    elif "ElectricCA" in (initial_url or "") or "CertCaApply" in (initial_url or ""):
        should_close = True
        close_reason = "憑證申請頁面"
    elif not initial_url or initial_url.lower() == "about:blank":
        # about:blank — 先不關閉，等一下看是否導航到其他 URL
        pass

    if should_close:
        print(f"      🔄 立即關閉 popup: {close_reason}")
        try:
            new_page.close()
        except Exception as e:
            print(f"      ⚠️ 關閉失敗: {e}")
        return

    # 對於不確定的頁面，等待一小段時間看 URL 變化
    try:
        new_page.wait_for_load_state("domcontentloaded", timeout=3000)
    except Exception:
        pass

    try:
        new_page.wait_for_timeout(1000)
    except Exception:
        pass

    url = ""
    title = ""
    try:
        url = new_page.url
        title = new_page.title()
    except Exception:
        # 頁面可能已被關閉
        print(f"      ⚠️ 頁面已關閉")
        return

    print(f"      載入後 URL: {url or '(空白)'}")
    print(f"      標題: {title or '(空白)'}")

    # 再次判斷是否需要關閉
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
        # 空白頁面 — 關閉它
        print(f"      🔄 關閉空白頁面")
        try:
            new_page.close()
        except Exception:
            pass
        return

    # 如果到這裡，頁面是有意義的，保留它
    print(f"      💡 保留此視窗")

    # 截圖和存 HTML
    ts = time.strftime("%H%M%S")
    try:
        new_page.screenshot(path=str(OUTPUT_DIR / f"popup_{ts}.png"))
        print(f"      📸 截圖: popup_{ts}.png")
    except Exception as e:
        print(f"      ⚠️ 截圖失敗: {e}")

    try:
        html = new_page.content()
        html_path = OUTPUT_DIR / f"popup_{ts}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"      📄 HTML 已存: popup_{ts}.html ({len(html)} chars)")
    except Exception as e:
        print(f"      ⚠️ 無法讀取內容: {e}")


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
        # 嘗試使用 Edge（支援 ActiveX/COM 憑證元件），若無則退回 Chromium
        browser_channel = "msedge"
        launch_args = [
            "--disable-popup-blocking",
            "--disable-features=PopupBlocker",
        ]
        try:
            print("🚀 啟動瀏覽器（嘗試 Edge / persistent context）...")
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

        # ── 註冊事件處理器 ──
        context.on("page", on_page_created)
        # 用 context.on("dialog") 處理所有頁面（含 iframe）的 alert
        context.on("dialog", on_dialog)

        page = context.pages[0] if context.pages else context.new_page()

        try:
            print(f"\n🌐 開啟: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            print(f"   頁面: {page.url[:80]}")
            print(f"   標題: {page.title()}")

            # 注入 window.open 攔截器（不干擾原始行為，只記錄）
            print("\n   🔧 注入 window.open 攔截器...")
            try:
                page.evaluate("""() => {
                    const originalOpen = window.open;
                    window.__popupLog = [];
                    window.open = function(...args) {
                        window.__popupLog.push({
                            url: args[0] || '',
                            target: args[1] || '',
                            features: args[2] || '',
                            time: new Date().toISOString()
                        });
                        const newWin = originalOpen.apply(this, args);
                        return newWin;
                    };
                }""")
            except Exception as e:
                print(f"   ⚠️ 注入攔截器失敗（可能頁面已導航）: {e}")

            # 如果有 alert 自動跳出，dialog handler 會自動按 OK
            # 等一下讓 alert 處理完畢
            page.wait_for_timeout(2000)

            if alert_log:
                print(f"\n   📋 已自動處理 {len(alert_log)} 個 alert：")
                for a in alert_log:
                    print(f"      [{a['type']}] {a['message'][:100]}")

            # 登入後頁面可能已導航，檢查當前頁面
            try:
                current_url = page.url
                if "default" in current_url or "main" in current_url.lower():
                    print(f"\n   ✅ 已登入！當前頁面: {current_url[:80]}")
                    # 重新注入攔截器（因為頁面已導航）
                    try:
                        page.evaluate("""() => {
                            if (!window.__popupLog) {
                                const originalOpen = window.open;
                                window.__popupLog = [];
                                window.open = function(...args) {
                                    window.__popupLog.push({
                                        url: args[0] || '',
                                        target: args[1] || '',
                                        features: args[2] || '',
                                        time: new Date().toISOString()
                                    });
                                    const newWin = originalOpen.apply(this, args);
                                    return newWin;
                                };
                            }
                        }""")
                    except Exception:
                        pass
                    # 也對 iframe 注入
                    try:
                        for frame in page.frames:
                            if frame != page.main_frame:
                                try:
                                    frame.evaluate("""() => {
                                        if (!window.__popupLog) {
                                            const originalOpen = window.open;
                                            window.__popupLog = window.top.__popupLog || [];
                                            window.open = function(...args) {
                                                window.__popupLog.push({
                                                    url: args[0] || '',
                                                    target: args[1] || '',
                                                    features: args[2] || '',
                                                    time: new Date().toISOString()
                                                });
                                                const newWin = originalOpen.apply(this, args);
                                                return newWin;
                                            };
                                        }
                                    }""")
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except Exception:
                pass

            all_results = {}

            for step_name, prompt in steps:
                alert_log.clear()  # 清除上一步的 alert 紀錄

                print(f"\n📋 {prompt}")
                print("   💡 alert 會自動按 OK")
                print("   💡 如果跳出空白視窗，那是 window.open('about:Blank') 開的")
                print("   💡 請在空白視窗中手動操作（如果需要），或忽略它")
                input("   👉 完成後按 Enter 繼續...")

                # 檢查 window.open 攔截紀錄
                try:
                    popup_log = page.evaluate("() => window.__popupLog || []")
                    if popup_log:
                        print(f"   🔍 window.open 被呼叫了 {len(popup_log)} 次：")
                        for call in popup_log:
                            print(f"      URL: {call.get('url', '(空)')[:80]}")
                            print(f"      Target: {call.get('target', '')}")
                            print(f"      Features: {call.get('features', '')[:80]}")
                except Exception:
                    pass

                # 截圖（加 try-except 避免頁面已關閉）
                try:
                    page.screenshot(path=str(OUTPUT_DIR / f"screenshot_{step_name}.png"))
                except Exception as e:
                    print(f"   ⚠️ 截圖失敗: {e}")

                # 如果有新開的 popup，也截圖所有頁面
                all_pages = context.pages
                if len(all_pages) > 1:
                    print(f"   📄 目前有 {len(all_pages)} 個瀏覽器視窗")
                    for i, pg in enumerate(all_pages):
                        try:
                            pg_url = pg.url
                            pg.screenshot(path=str(OUTPUT_DIR / f"screenshot_{step_name}_page{i}.png"))
                            print(f"      Page {i}: {pg_url[:80]} → 截圖已存")
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
                try:
                    all_results[step_name] = {
                        "url": page.url,
                        "title": page.title(),
                        "tables_count": len(tables),
                        "alerts": alert_log.copy(),
                    }
                except Exception:
                    all_results[step_name] = {
                        "url": "(頁面已關閉)",
                        "title": "",
                        "tables_count": len(tables),
                        "alerts": alert_log.copy(),
                    }

            # 額外頁面
            while True:
                extra = input("\n🎯 其他頁面？（名稱 / Enter 結束）: ").strip()
                if not extra:
                    break
                input(f"   導航到「{extra}」後按 Enter...")
                try:
                    page.screenshot(path=str(OUTPUT_DIR / f"screenshot_{extra}.png"))
                except Exception:
                    pass
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
            try:
                page.screenshot(path=str(OUTPUT_DIR / "interrupted.png"))
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
            print("\n🔒 瀏覽器已關閉（profile 已保存）")
            print(f"   Profile: {USER_DATA_DIR}")


if __name__ == "__main__":
    main()