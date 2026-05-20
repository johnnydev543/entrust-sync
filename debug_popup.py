#!/usr/bin/env python3
"""
華南永昌 — Popup 偵錯工具
==========================
分析登入頁面的 popup 行為，找出為什麼新視窗是空白的。
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
USER_DATA_DIR = SCRIPT_DIR / "browser_profile"

LOGIN_URL = "https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx"

# 收集所有事件
events_log = []


def log_event(event_type, detail):
    msg = f"[{time.strftime('%H:%M:%S')}] {event_type}: {detail}"
    print(msg)
    events_log.append({"time": time.strftime("%H:%M:%S"), "type": event_type, "detail": detail})


def main():
    print("=" * 60)
    print("華南永昌 — Popup 偵錯工具")
    print("=" * 60)
    print()
    print("這個工具會：")
    print("  1. 開啟登入頁面")
    print("  2. 監聽所有 popup / 新頁面事件")
    print("  3. 分析頁面中的 JS window.open 呼叫")
    print("  4. 你手動登入後，觀察 popup 行為")
    print()

    with sync_playwright() as p:
        print("啟動 Edge 瀏覽器...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            channel="msedge",
            headless=False,
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
            args=[
                "--disable-popup-blocking",
                "--disable-features=PopupBlocker",
            ],
        )

        # 監聽所有新頁面事件
        def on_page_created(new_page):
            log_event("PAGE_CREATED", f"url={new_page.url}")
            # 等待導航
            try:
                new_page.wait_for_load_state("load", timeout=15000)
            except Exception:
                log_event("PAGE_LOAD_TIMEOUT", f"url={new_page.url}")

            try:
                url = new_page.url
                title = new_page.title()
                log_event("PAGE_INFO", f"url={url}, title={title}")
            except Exception as e:
                log_event("PAGE_INFO_ERROR", str(e))

            # 截圖
            ts = time.strftime("%H%M%S")
            try:
                new_page.screenshot(path=str(OUTPUT_DIR / f"debug_popup_{ts}.png"))
                log_event("SCREENSHOT", f"debug_popup_{ts}.png")
            except Exception as e:
                log_event("SCREENSHOT_ERROR", str(e))

            # 存 HTML
            try:
                html = new_page.content()
                html_path = OUTPUT_DIR / f"debug_popup_{ts}.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
                log_event("HTML_SAVED", f"debug_popup_{ts}.html ({len(html)} chars)")

                # 分析 HTML
                if len(html) < 200:
                    log_event("HTML_SHORT", f"HTML is very short: {html[:300]}")
                else:
                    # 檢查有沒有 form, iframe, script
                    has_form = "<form" in html.lower()
                    has_iframe = "<iframe" in html.lower() or "<frame" in html.lower()
                    has_script = "<script" in html.lower()
                    log_event("HTML_ANALYSIS", f"form={has_form}, iframe={has_iframe}, script={has_script}")
            except Exception as e:
                log_event("HTML_ERROR", str(e))

            # 註冊 dialog handler（不自動按，讓使用者看到）
            def on_popup_dialog(dialog, pg=new_page):
                log_event("POPUP_DIALOG", f"type={dialog.type}, msg={dialog.message[:200]}")
                dialog.accept()

            new_page.on("dialog", on_popup_dialog)

            # 監聽新頁面內的 frame 導航
            new_page.on("framenavigated", lambda frame: (
                log_event("FRAME_NAV", f"url={frame.url[:100]}")
            ))

            # 監聽新頁面內的 request
            def on_response(response):
                log_event("RESPONSE", f"url={response.url[:100]}, status={response.status}")

            new_page.on("response", on_response)

        context.on("page", on_page_created)

        page = context.pages[0] if context.pages else context.new_page()

        # 監聽主頁面 dialog（不自動按 OK，讓使用者看到）
        def on_main_dialog(dialog):
            log_event("DIALOG", f"type={dialog.type}, msg={dialog.message[:200]}")
            # 不自動按 OK，讓使用者決定
            # 但如果是 confirm，需要回應才能繼續
            if dialog.type == "alert":
                dialog.accept()
            else:
                # confirm / prompt — 自動按 OK 讓流程繼續
                dialog.accept()

        page.on("dialog", on_main_dialog)

        page.on("framenavigated", lambda frame: (
            log_event("FRAME_NAV", f"url={frame.url[:100]}")
        ))

        # 監聽所有 request/response
        def on_main_response(response):
            url = response.url
            # 只記錄非靜態資源的 request
            if any(ext in url for ext in ['.js', '.aspx', '.asp', '.php', '.do', '.action']):
                log_event("MAIN_RESPONSE", f"url={url[:120]}, status={response.status}")

        page.on("response", on_main_response)

        # 注入 JS 攔截 window.open
        print(f"\n開啟: {LOGIN_URL}")
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)

        # 注入 window.open 攔截器（不使用 console.log，避免干擾頁面 JS）
        print("\n注入 window.open 攔截器...")
        page.evaluate("""() => {
            const originalOpen = window.open;
            window.__openCalls = [];
            window.open = function(...args) {
                window.__openCalls.push({
                    url: args[0] || '',
                    target: args[1] || '',
                    features: args[2] || '',
                    time: new Date().toISOString()
                });
                return originalOpen.apply(this, args);
            };

            // 也攔截 showModalDialog (舊版 IE)
            if (window.showModalDialog) {
                const originalModal = window.showModalDialog;
                window.showModalDialog = function(...args) {
                    window.__openCalls.push({
                        type: 'showModalDialog',
                        url: args[0] || '',
                        time: new Date().toISOString()
                    });
                    return originalModal.apply(this, args);
                };
            }

            // 攔截 form target
            document.addEventListener('submit', function(e) {
                const form = e.target;
                if (form && form.target && form.target !== '_self') {
                    window.__openCalls.push({
                        type: 'form_submit',
                        action: form.action || '',
                        target: form.target,
                        method: form.method || 'GET',
                        time: new Date().toISOString()
                    });
                }
            }, true);
        }""")

        # 不攔截 console 訊息，避免干擾頁面 JS

        print("\n" + "=" * 60)
        print("偵錯模式已啟動！")
        print("=" * 60)
        print()
        print("請在瀏覽器中操作：")
        print("  1. 輸入帳號密碼")
        print("  2. 按登入")
        print("  3. 輸入 OTP")
        print("  4. 觀察 popup 行為")
        print()
        print("所有事件都會記錄在終端和 output/debug_events.json")
        print()

        input("👉 完成登入操作後按 Enter 繼續...")

        # 檢查 window.open 攔截結果
        print("\n--- window.open 攔截結果 ---")
        open_calls = page.evaluate("() => window.__openCalls || []")
        if open_calls:
            print(f"攔截到 {len(open_calls)} 次 window.open 呼叫：")
            for call in open_calls:
                print(f"  {json.dumps(call, ensure_ascii=False)}")
        else:
            print("沒有攔截到 window.open 呼叫")

        # 檢查所有頁面
        print(f"\n--- 目前所有頁面 ({len(context.pages)}) ---")
        for i, pg in enumerate(context.pages):
            try:
                url = pg.url
                title = pg.title()
                print(f"  Page {i}: url={url[:100]}, title={title}")
            except Exception as e:
                print(f"  Page {i}: (無法讀取: {e})")

        # 檢查所有 frame
        print(f"\n--- 主頁面 frames ({len(page.frames)}) ---")
        for i, frame in enumerate(page.frames):
            print(f"  Frame {i}: url={frame.url[:100]}")

        # 截圖主頁面
        page.screenshot(path=str(OUTPUT_DIR / "debug_main.png"))
        print(f"\n主頁面截圖: output/debug_main.png")

        # 存主頁面 HTML
        main_html = page.content()
        with open(OUTPUT_DIR / "debug_main.html", "w", encoding="utf-8") as f:
            f.write(main_html)
        print(f"主頁面 HTML: output/debug_main.html ({len(main_html)} chars)")

        # 存事件紀錄
        with open(OUTPUT_DIR / "debug_events.json", "w", encoding="utf-8") as f:
            json.dump(events_log, f, ensure_ascii=False, indent=2)
        print(f"事件紀錄: output/debug_events.json ({len(events_log)} events)")

        input("\n👉 按 Enter 關閉瀏覽器...")
        context.close()
        print("完成！")


if __name__ == "__main__":
    main()