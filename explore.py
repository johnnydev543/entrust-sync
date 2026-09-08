#!/usr/bin/env python3
"""
華南永昌持股同步 — 探索模式 v5
===================================

v5 改進：
- 自動填入帳號密碼（從 .env 讀取）
- addInitScript 自動攔截 alert/confirm（頁面載入前就注入）
- 以非阻塞方式記錄 popup，不干預登入與憑證流程
- 驗證碼仍需手動輸入（提示使用者）
- persistent context：憑證只需安裝一次

Alert 流程：
  1. addInitScript 在每個頁面載入前覆蓋 window.alert/confirm
  2. Alert: 錯誤代碼 5010 → 自動吞掉（console.log）
  3. Alert: 您尚未下載憑證 → 自動吞掉
  4. Popup window → 僅記錄，不干預網站流程
"""

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from inventory_export import convert_inventory_xls, inventory_item_from_values
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
    """以非阻塞方式記錄新視窗，不干預網站的登入與憑證流程。"""
    print(f"   🪟 [Popup] 新視窗開啟！")

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


def capture_aggregate_inventory(page) -> list[dict]:
    """擷取「證券彙總庫存查詢」的 25 欄明細，轉成穩定欄位。"""
    positions = {}

    for frame in page.frames:
        try:
            for table in frame.locator("table").all():
                for row in table.locator("tr").all():
                    cells = row.locator(":scope > td").all()
                    if len(cells) != 25:
                        continue
                    values = [(cell.inner_text() or "").strip() for cell in cells]
                    item = inventory_item_from_values(values)
                    if item:
                        positions[item["code"]] = item
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
                with page.expect_download(timeout=30_000) as download_info:
                    button.click()
                download = download_info.value
                suffix = Path(download.suggested_filename).suffix or ".xls"
                filepath = OUTPUT_DIR / f"aggregate_inventory_{date.today().isoformat()}{suffix}"
                download.save_as(str(filepath))
                print(f"   📥 庫存 XLS 已存: {filepath}")
                json_path, csv_path, data = convert_inventory_xls(filepath)
                print(f"   ✅ 已轉成 UTF-8 JSON（{len(data)} 筆）: {json_path}")
                print(f"   ✅ 已轉成 UTF-8 CSV: {csv_path}")
                return filepath
            except Exception:
                continue
    print("   ⚠️ 找不到庫存 XLS 匯出按鈕，或下載未開始")
    return None


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
    # 讀取 .env 帳密
    load_dotenv(SCRIPT_DIR / ".env")
    account = os.getenv("ENTRUST_ACCOUNT", "")
    password = os.getenv("ENTRUST_PASSWORD", "")

    print("🏦 華南永昌持股同步 — 探索模式 v5")
    print("=" * 45)
    print()
    print("🔑 v5 改進：")
    print("   ✅ addInitScript 自動攔截 alert/confirm（頁面載入前注入）")
    print("   ✅ 以非阻塞方式記錄 popup")
    print("   ✅ 自動填入帳號密碼（從 .env 讀取）")
    print("   ✅ persistent context（憑證只需裝一次）")
    if account:
        print(f"   ✅ 帳號: {account[:3]}***（已從 .env 讀取）")
    else:
        print("   ⚠️ 未設定 .env，帳密需手動輸入")
    print()
    print("⚠️ 驗證碼仍需手動輸入")
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
            "--disable-blink-features=AutomationControlled",
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

        # ── 注入 addInitScript：在每個頁面載入前覆蓋 alert/confirm ──
        # 這是關鍵：addInitScript 會在頁面的任何 JS 執行前就注入
        # 比 page.evaluate() 更可靠，因為它不會被頁面導航清除
        context.add_init_script("""
            // 客戶專區會在 navigator.webdriver 為 true 時移除 ElectricCA
            // 等功能路由，結果看起來像站方 404。
            Object.defineProperty(Navigator.prototype, 'webdriver', {
                get: () => false,
                configurable: true
            });
            // 覆蓋 window.alert — 自動吞掉，記錄到 console
            window.alert = function(msg) {
                console.log('[ALERT BLOCKED] ' + String(msg));
                return undefined;
            };
            // 覆蓋 window.confirm — 自動按確定
            window.confirm = function(msg) {
                console.log('[CONFIRM BLOCKED] ' + String(msg));
                return true;
            };
            // 覆蓋 window.open — 阻擋不需要的 popup
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

            # ── 自動填入帳號密碼 ──
            if account and password:
                print("\n   🔑 自動填入帳號密碼...")
                try:
                    # 帳號
                    for sel in ['input[name="txtLoginID"]', 'input[id="txtLoginID"]',
                                'input[placeholder*="身分證"]', 'input[type="text"]']:
                        try:
                            el = page.locator(sel).first
                            if el.is_visible(timeout=2000):
                                el.click()
                                el.fill(account)
                                print(f"      ✅ 帳號已填入")
                                break
                        except Exception:
                            continue

                    # 密碼
                    for sel in ['input[name="password"]', 'input[type="password"]']:
                        try:
                            el = page.locator(sel).first
                            if el.is_visible(timeout=2000):
                                el.click()
                                el.fill(password)
                                print(f"      ✅ 密碼已填入")
                                break
                        except Exception:
                            continue

                    print("   ⚠️ 請手動輸入驗證碼，然後按登入")
                except Exception as e:
                    print(f"   ⚠️ 自動填入失敗: {e}")
                    print("   💡 請手動輸入帳號密碼和驗證碼")
            else:
                print("\n   ⚠️ 未設定 .env，請手動輸入帳號密碼和驗證碼")

            # 注入 window.open 攔截器（不干擾原始行為，只記錄）
            # 注意：addInitScript 已經覆蓋了 window.open，這裡只記錄
            print("\n   🔧 注入 popup 記錄器...")
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
                if step_name == "holdings":
                    inventory = capture_aggregate_inventory(page)
                    inventory_path = OUTPUT_DIR / f"aggregate_inventory_{date.today().isoformat()}.json"
                    with open(inventory_path, "w", encoding="utf-8") as f:
                        json.dump({"date": date.today().isoformat(),
                                   "source": "華南永昌證券",
                                   "positions": inventory}, f, ensure_ascii=False, indent=2)
                    print(f"   💾 已存: {inventory_path}（{len(inventory)} 筆）")
                    download_aggregate_inventory_xls(page)
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
