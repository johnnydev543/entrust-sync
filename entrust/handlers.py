"""互動同步與診斷工具共用的 alert/popup 事件處理。"""

import time

alert_log = []


def reset_alert_log():
    """清除 alert 紀錄（探索模式每一步驟前會呼叫）。"""
    alert_log.clear()


def on_dialog(dialog):
    """自動處理 JavaScript alert/confirm/prompt — 全部自動按 OK / 確定。

    必須用 dialog.accept()，否則瀏覽器會暫停等待使用者回應。
    """
    msg = dialog.message
    print(f"   💬 [Alert] {dialog.type}: {msg[:200]}")
    alert_log.append({
        "type": dialog.type,
        "message": msg,
        "time": time.strftime("%H:%M:%S"),
    })
    try:
        # 如果 dialog 已經被關閉（例如使用者手動按了），忽略錯誤
        dialog.accept()
    except Exception:
        pass


def on_popup(new_page):
    """以非阻塞方式記錄彈出視窗，不干預網站的登入與憑證流程。"""
    print("   🪟 [Popup] 新視窗！")

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
