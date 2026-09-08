#!/usr/bin/env python3
"""
華南永昌持股同步 — 探索模式 v5
===================================

v5: 共用邏輯收斂到 entrust/ 套件（常數、alert/popup handler、表格擷取、
    瀏覽器啟動、帳密填入），此檔只保留探索模式自己的流程：
    popup 記錄、多視窗截圖、save_step、full_sync_*.json 總結。

Alert 流程：
  1. addInitScript 在每個頁面載入前覆蓋 window.alert/confirm
  2. Alert: 錯誤代碼 5010 → 自動吞掉（console.log）
  3. Alert: 您尚未下載憑證 → 自動吞掉
  4. Popup window → 僅記錄，不干預網站流程
"""

import json
from datetime import date

from playwright.sync_api import sync_playwright

from entrust import (
    LOGIN_URL,
    OUTPUT_DIR,
    USER_DATA_DIR,
    alert_log,
    capture_aggregate_inventory,
    capture_all_tables,
    download_aggregate_inventory_xls,
    launch_browser,
    reset_alert_log,
    save_step,
)
from entrust.login import fill_credentials, load_credentials


def main():
    global alert_log

    print()
    # 讀取 .env 帳密
    account, password = load_credentials()

    print("🏦 華南永昌持股同步 — 探索模式 v5")
    print("=" * 45)
    print()
    print("🔑 登入方式：")
    if account:
        print(f"   ✅ 將從 .env 自動填入帳號: {account[:3]}***")
    else:
        print("   ℹ️ .env 未設定帳密，請在網頁上手動輸入")
    print("   ℹ️ 圖形驗證碼需手動輸入")
    print()

    steps = [
        ("login", "請在瀏覽器中完成登入"),
        ("holdings", "請導航到「持股明細」或「庫存查詢」頁面"),
        ("transactions", "請導航到「交易紀錄」或「成交查詢」頁面"),
    ]

    with sync_playwright() as p:
        # Edge → Chromium fallback、init script、alert/popup handler
        # 全部收斂在 entrust.browser.launch_browser
        context, _ = launch_browser(p)

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
                    fill_credentials(page, account, password)
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
                reset_alert_log()  # 清除上一步的 alert 紀錄

                print(f"\n📋 {prompt}")
                if step_name == "login":
                    print("   ℹ️ 請依網頁提示輸入驗證碼；若網站要求憑證，也請依畫面完成")
                    input("   👉 看到登入後的主畫面時，按 Enter 繼續...")
                else:
                    input("   👉 到達指定頁面後，按 Enter 開始擷取...")

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

                save_step(step_name, page, tables, alert_log.copy())
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
                save_step(extra, page, tables, alert_log.copy())

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
