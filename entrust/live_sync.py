"""常駐瀏覽器工作執行緒：使用者登入後，供 API 自動導航與擷取。"""

import json
import queue
import threading
from concurrent.futures import Future
from datetime import date
from typing import Optional

from playwright.sync_api import sync_playwright

from entrust.capture import capture_aggregate_inventory, capture_all_tables
from entrust.config import DEFAULT_TIMEOUT, LOGIN_URL, MAIN_URL, OUTPUT_DIR
from entrust.handlers import alert_log, reset_alert_log
from entrust.browser import launch_browser, save_session_cookies


class LoginRequiredError(RuntimeError):
    """瀏覽器尚未完成登入。"""


class NavigationError(RuntimeError):
    """找不到指定查詢功能。"""


class BrowserWorker:
    """讓所有 Playwright 操作固定在同一執行緒內執行。"""

    def __init__(self):
        self._tasks = queue.Queue()
        self._thread = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._logged_in = False
        self._current_url = ""
        self._page_urls = []
        self._known_pages = []
        self._error = ""

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="entrust-browser", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._tasks.put(None)
        if self._thread:
            self._thread.join(timeout=10)

    def status(self) -> dict:
        return {
            "browser_ready": self._ready_event.is_set(),
            "logged_in": self._logged_in,
            "current_url": self._current_url,
            "page_urls": self._page_urls,
            "error": self._error or None,
        }

    def submit(self, operation: str, **kwargs):
        if not self._ready_event.wait(timeout=30):
            raise RuntimeError("瀏覽器尚未完成啟動")
        future = Future()
        self._tasks.put((future, operation, kwargs))
        return future.result(timeout=90)

    def _run(self):
        try:
            with sync_playwright() as playwright:
                context, _ = launch_browser(playwright)
                self._known_pages = list(context.pages)
                context.on("page", self._remember_page)
                page = context.pages[0] if context.pages else context.new_page()

                # 先驗證 persistent profile 中的既有 session。cookie 存在不代表
                # 伺服器端 session 仍有效，因此直接開主頁並觀察是否被導回登入頁。
                page = self._update_login_state(context, page)
                if not self._logged_in:
                    page.goto(MAIN_URL, wait_until="networkidle", timeout=DEFAULT_TIMEOUT)
                    page = self._update_login_state(context, page)
                if not self._logged_in and "login" not in page.url.lower():
                    page.goto(LOGIN_URL, wait_until="networkidle", timeout=DEFAULT_TIMEOUT)
                    page = self._update_login_state(context, page)
                # Chromium/Playwright 可能保留一個 about:blank 分頁並將它放在前景。
                # API 已自行恢復 cookies 並導航華南頁面，不需要保留空白分頁。
                for extra_page in list(context.pages):
                    if extra_page is not page and extra_page.url == "about:blank":
                        extra_page.close()
                page.bring_to_front()
                self._ready_event.set()
                if self._logged_in:
                    print("✅ 已沿用 browser_profile 中仍有效的登入 session")
                else:
                    print("🔑 Session 不存在或已過期，請在瀏覽器手動完成登入")

                try:
                    while not self._stop_event.is_set():
                        page = self._update_login_state(context, page)
                        try:
                            task = self._tasks.get(timeout=1)
                        except queue.Empty:
                            continue
                        if task is None:
                            break
                        future, operation, kwargs = task
                        try:
                            page = self._ensure_authenticated(context, page)
                            if not self._logged_in:
                                raise LoginRequiredError("請先在已開啟的瀏覽器完成登入")
                            result = self._execute(context, page, operation, kwargs)
                            future.set_result(result)
                        except Exception as exc:
                            self._error = str(exc)
                            future.set_exception(exc)
                finally:
                    save_session_cookies(context)
                    context.close()
        except Exception as exc:
            self._error = str(exc)
            self._ready_event.set()

    def _remember_page(self, page):
        """保留登入流程新開的頁面，避免舊站 popup 轉接後遺失主頁參照。"""
        if page not in self._known_pages:
            self._known_pages.append(page)

    def _update_login_state(self, context, preferred_page):
        """從所有視窗找出真正已登入的主頁，避免一直盯著舊登入頁。"""
        was_logged_in = self._logged_in
        candidates = []
        page_urls = []
        pages = list(context.pages)
        for known_page in self._known_pages:
            if known_page not in pages:
                pages.append(known_page)
        for candidate in pages:
            try:
                url = candidate.url.lower()
                if candidate.is_closed():
                    continue
                page_urls.append(candidate.url)
                if "eztrade.entrust.com.tw" not in url:
                    continue
                if "default.aspx" in url:
                    candidates.insert(0, candidate)
                elif "/hnsweb/main" in url:
                    candidates.append(candidate)
                elif "/hnsweb/ts" in url:
                    candidates.append(candidate)
            except Exception:
                continue
        self._page_urls = page_urls

        if candidates:
            active_page = candidates[0]
            self._current_url = active_page.url
            self._logged_in = True
            self._error = ""
            if not was_logged_in:
                save_session_cookies(context)
            return active_page

        try:
            self._current_url = preferred_page.url
        except Exception:
            self._current_url = ""
        self._logged_in = False
        return preferred_page

    def _ensure_authenticated(self, context, page):
        page = self._update_login_state(context, page)
        if not self._logged_in:
            # 使用者可能已在華南另開的原生視窗完成登入，但該 window
            # 不在 Playwright 的 page 清單中。兩者仍共享 browser_profile
            # cookie；重新開主頁即可接回有效 session。
            page.goto(MAIN_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
            page = self._update_login_state(context, page)
        return page

    def _execute(self, context, page, operation: str, kwargs: dict):
        if operation == "holdings":
            return self._capture_holdings(page)
        if operation == "transactions":
            return self._capture_transactions(context, page, kwargs["transaction_date"], False)
        if operation == "history":
            return self._capture_transactions(context, page, kwargs.get("transaction_date") or date.today().isoformat(), True)
        if operation == "statement_today":
            return self._query_statement(page, "today", kwargs.get("stock_code"))
        if operation == "statement_history":
            return self._query_statement(
                page,
                "history",
                kwargs.get("stock_code"),
                kwargs.get("date_from"),
                kwargs.get("date_to"),
            )
        if operation == "profit_loss":
            return self._query_profit_loss(page, kwargs["realized"], kwargs.get("stock_code"))
        raise ValueError(f"未知操作：{operation}")

    @staticmethod
    def _click_text(page, labels: list[str]) -> bool:
        """跨 frame 依 fallback 順序點擊第一個可見的選單文字。"""
        for label in labels:
            for frame in page.frames:
                for selector in [
                    f'a:has-text("{label}")',
                    f'button:has-text("{label}")',
                    f'input[value*="{label}"]',
                    f'td:has-text("{label}")',
                ]:
                    try:
                        target = frame.locator(selector).first
                        if target.is_visible(timeout=300):
                            target.click()
                            page.wait_for_timeout(1000)
                            return True
                    except Exception:
                        continue
        return False

    def _navigate(self, page, parents: list[str], targets: list[str]):
        self._click_text(page, parents)
        if not self._click_text(page, targets):
            raise NavigationError(f"找不到查詢功能：{' / '.join(targets)}")
        page.wait_for_timeout(2000)

    @staticmethod
    def _goto_content(page, relative_url: str):
        """直接在帳務內容 iframe 導航，避開不穩定的舊式浮動選單。"""
        target_url = f"https://eztrade.entrust.com.tw/hnsweb/{relative_url}"
        candidates = []
        # default.aspx 的 frameset 在 DOMContentLoaded 之後才逐步建立，最多等 5 秒。
        for _ in range(10):
            candidates = []
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                url = frame.url.lower()
                if "/hnsweb/menu.aspx" in url or "/hnsweb/querymatchmsg.aspx" in url:
                    continue
                if "/hnsweb/" in url:
                    candidates.append(frame)
            if candidates:
                break
            page.wait_for_timeout(500)
        if not candidates:
            # 部分華南登入轉接只把 session 帶回頂層頁面，未建立 frameset。
            # 查詢頁可獨立運作，因此直接在頂層導航，擷取函式也會讀 main frame。
            page.goto(target_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
            page.wait_for_timeout(1000)
            return page.main_frame

        frame = candidates[0]
        frame.goto(target_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
        frame.wait_for_timeout(1000)
        return frame

    def _open_statement(self, page, statement_type: str):
        filename = "TS02031.aspx" if statement_type == "today" else "TS0203.aspx"
        label = "當日對帳單查詢" if statement_type == "today" else "歷史對帳單查詢"
        try:
            return self._goto_content(page, filename)
        except Exception as direct_error:
            self._click_text(page, ["證券帳務"])
            if self._click_text(page, [label]):
                page.wait_for_timeout(1000)
                for frame in page.frames:
                    if filename.lower() in frame.url.lower():
                        return frame
            raise NavigationError(f"無法開啟「{label}」：{direct_error}") from direct_error
        raise NavigationError(f"已點擊「{label}」，但找不到 {filename} 內容 frame")

    @staticmethod
    def _submit_statement(frame):
        for selector in [
            'input[type="image"][src*="BT_check" i]',
            'input[type="submit"]',
            'button:has-text("查詢")',
            'button:has-text("提交")',
        ]:
            try:
                button = frame.locator(selector).first
                if button.is_visible(timeout=500):
                    button.click()
                    frame.wait_for_timeout(1500)
                    return
            except Exception:
                continue
        raise NavigationError("找不到對帳單查詢按鈕")

    @staticmethod
    def _statement_result(frame) -> tuple[dict, list[dict], bool]:
        totals = {}
        entries = []
        empty = False
        try:
            empty = "查無資料" in frame.locator("body").inner_text()
        except Exception:
            pass

        for table in frame.locator("table").all():
            try:
                raw_rows = []
                for row in table.locator("tr").all():
                    cells = [(cell.inner_text() or "").strip() for cell in row.locator(":scope > th, :scope > td").all()]
                    if cells:
                        raw_rows.append(cells)
                if not raw_rows:
                    continue
                first = raw_rows[0]
                if "成交價金" in first:
                    for index in range(0, len(first) - 1, 2):
                        if first[index]:
                            totals[first[index]] = first[index + 1]
                if "成交日期" in first:
                    for values in raw_rows[1:]:
                        entry = {
                            header: values[index] if index < len(values) else ""
                            for index, header in enumerate(first)
                            if header
                        }
                        if any(entry.values()):
                            entries.append(entry)
            except Exception:
                continue
        return totals, entries, empty

    def _query_statement(
        self,
        page,
        statement_type: str,
        stock_code: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict:
        frame = self._open_statement(page, statement_type)
        text_inputs = frame.locator('input[type="text"]')
        expected = 1 if statement_type == "today" else 3
        if text_inputs.count() < expected:
            raise NavigationError("對帳單查詢欄位數量與預期不符")

        text_inputs.nth(0).fill(stock_code or "")
        if statement_type == "history":
            text_inputs.nth(1).fill((date_from or "").replace("-", "/"))
            text_inputs.nth(2).fill((date_to or "").replace("-", "/"))
        self._submit_statement(frame)
        totals, entries, empty = self._statement_result(frame)
        return {
            "statement_type": statement_type,
            "stock_code": stock_code,
            "date_from": date_from if statement_type == "history" else date.today().isoformat(),
            "date_to": date_to if statement_type == "history" else date.today().isoformat(),
            "count": len(entries),
            "empty": empty,
            "totals": totals,
            "entries": entries,
        }

    def _open_profit_loss(self, page):
        try:
            return self._goto_content(page, "TS0211.aspx?drpSum=2")
        except Exception as direct_error:
            self._click_text(page, ["證券帳務"])
            if self._click_text(page, ["庫存（未實現）損益", "庫存(未實現)損益"]):
                page.wait_for_timeout(1000)
                for frame in page.frames:
                    if "TS0211.aspx" in frame.url:
                        return frame
            raise NavigationError(f"無法開啟庫存損益：{direct_error}") from direct_error

    @staticmethod
    def _profit_loss_sections(frame) -> list[dict]:
        sections = []
        for table in frame.locator("table").all():
            try:
                rows = []
                for row in table.locator("tr").all():
                    values = [(cell.inner_text() or "").strip() for cell in row.locator(":scope > th, :scope > td").all()]
                    if values:
                        rows.append(values)
                if len(rows) < 2:
                    continue
                headers = [" ".join(value.split()) for value in rows[0]]
                if "股票名稱" not in headers:
                    continue
                if headers[0] == "下單" and len(rows[1]) == len(headers) + 1:
                    headers = ["序號", "下單"] + headers[1:]

                entries = []
                total = None
                for values in rows[1:]:
                    normalized = values + [""] * max(0, len(headers) - len(values))
                    item = {header: normalized[index] for index, header in enumerate(headers) if header}
                    if "合計" in values:
                        total = item
                    elif any(item.values()):
                        entries.append(item)

                if "現價" in headers:
                    section_type = "unrealized_inventory"
                elif "買進 股價" in headers or "買進股價" in headers:
                    section_type = "day_trade_realized"
                elif "成交價" in headers:
                    section_type = "settled_inventory_realized"
                else:
                    section_type = "profit_loss"
                sections.append({
                    "type": section_type,
                    "count": len(entries),
                    "headers": headers,
                    "entries": entries,
                    "total": total,
                })
            except Exception:
                continue
        return sections

    def _query_profit_loss(self, page, realized: bool, stock_code: Optional[str]) -> dict:
        frame = self._open_profit_loss(page)
        stock_input = frame.locator('input[type="text"]').first
        if not stock_input.is_visible(timeout=1000):
            raise NavigationError("找不到庫存損益的個股代號欄位")
        stock_input.fill(stock_code or "")

        radios = frame.locator('input[type="radio"]')
        if radios.count() < 2:
            raise NavigationError("找不到已實現／未實現損益選項")
        radios.nth(0 if realized else 1).check()
        self._submit_statement(frame)
        sections = self._profit_loss_sections(frame)
        return {
            "type": "realized" if realized else "unrealized",
            "stock_code": stock_code,
            "count": sum(section["count"] for section in sections),
            "sections": sections,
        }

    def _capture_holdings(self, page) -> dict:
        reset_alert_log()
        try:
            self._goto_content(page, "TS0106.aspx?drpSum=1")
        except Exception as direct_error:
            try:
                self._navigate(
                    page,
                    ["證券帳務", "帳務查詢"],
                    ["彙總庫存查詢", "證券彙總庫存查詢", "彙總庫存", "庫存查詢", "持股明細"],
                )
            except Exception as menu_error:
                raise NavigationError(
                    f"無法直接開啟彙總庫存（{direct_error}）；選單導航也失敗（{menu_error}）"
                ) from menu_error
        positions = capture_aggregate_inventory(page)
        if not positions:
            raise NavigationError("已開啟庫存功能，但沒有擷取到持股資料")
        market_value = None
        for frame in page.frames:
            if "TS0106.aspx" not in frame.url:
                continue
            try:
                for row in frame.locator("tr").all():
                    values = [(cell.inner_text() or "").strip() for cell in row.locator(":scope > th, :scope > td").all()]
                    if "庫存市值" in values and len(values) > values.index("庫存市值") + 1:
                        market_value = values[values.index("庫存市值") + 1]
                        break
            except Exception:
                pass
        today = date.today().isoformat()
        payload = {
            "date": today,
            "source": "華南永昌證券",
            "market_value": market_value,
            "positions": positions,
        }
        path = OUTPUT_DIR / f"aggregate_inventory_{today}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**payload, "count": len(positions)}

    def _capture_transactions(self, context, page, transaction_date: str, historical: bool) -> dict:
        reset_alert_log()
        targets = (
            ["歷史成交查詢", "歷史交易查詢", "歷史交易", "交易明細"]
            if historical
            else ["成交查詢", "今日成交", "成交回報", "今日交易"]
        )
        self._navigate(page, ["帳務查詢", "交易查詢"], targets)
        tables = capture_all_tables(page)
        for index, extra_page in enumerate(context.pages):
            if extra_page == page:
                continue
            try:
                extra_tables = capture_all_tables(extra_page)
                for table in extra_tables:
                    table["source"] = f"page_{index}"
                tables.extend(extra_tables)
            except Exception:
                pass
        payload = {
            "date": transaction_date,
            "captured_at": date.today().isoformat(),
            "source": "華南永昌證券",
            "tables": tables,
            "alerts": alert_log.copy(),
        }
        path = OUTPUT_DIR / f"transactions_{transaction_date}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload


browser_worker = BrowserWorker()
