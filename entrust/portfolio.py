"""歷史對帳單分段與期初庫存計算。"""

import re
from datetime import date, timedelta


STOCK_PATTERN = re.compile(r"\(([^)]+)\)")


def history_windows(date_from: date, date_to: date) -> list[tuple[date, date]]:
    """將日期區間切成華南可接受的單次最多六個月。"""
    if date_from > date_to:
        raise ValueError("date_from 不可晚於 date_to")

    windows = []
    current = date_from
    while current <= date_to:
        end = min(current + timedelta(days=183), date_to)
        windows.append((current, end))
        current = end + timedelta(days=1)
    return windows


def aggregate_statements(chunks: list[dict], date_from: str, date_to: str) -> dict:
    """合併多段歷史對帳單，並保留各段查詢結果供核對。"""
    entries = []
    for chunk in chunks:
        entries.extend(chunk.get("entries", []))

    entries.sort(key=lambda item: item.get("成交日期", ""), reverse=True)
    return {
        "statement_type": "history_full",
        "date_from": date_from,
        "date_to": date_to,
        "chunk_count": len(chunks),
        "count": len(entries),
        "empty": not entries,
        "chunks": [
            {
                "date_from": chunk.get("date_from"),
                "date_to": chunk.get("date_to"),
                "count": chunk.get("count", 0),
                "empty": chunk.get("empty", False),
                "totals": chunk.get("totals", {}),
            }
            for chunk in chunks
        ],
        "entries": entries,
    }


def calculate_opening_inventory(
    current_positions: list[dict],
    entries: list[dict],
    as_of: str,
) -> dict:
    """用現有庫存反推指定日期開盤前的現股庫存數量。

    期初數量 = 現有數量 + 指定日後賣出 - 指定日後買進。
    僅處理現股買賣；融資、融券與無法辨識的列會列入 ignored_entries。
    """
    stocks = {}
    for position in current_positions:
        code = str(position.get("code", "")).strip().upper()
        if not code:
            continue
        summary = position.get("share_summary") or {}
        current_shares = int(summary.get("cash_shares", 0) or 0)
        stocks[code] = {
            "stock_code": code,
            "stock_name": position.get("name", ""),
            "opening_shares": current_shares,
            "current_shares": current_shares,
            "buys_after_as_of": 0,
            "sells_after_as_of": 0,
        }

    ignored_entries = []
    for entry in entries:
        trade_type = str(entry.get("類別", "")).replace("\n", "").strip()
        if not trade_type.startswith("現股") or not ("買" in trade_type or "賣" in trade_type):
            ignored_entries.append(entry)
            continue

        stock_label = str(entry.get("股票", "")).replace("\n", " ").strip()
        match = STOCK_PATTERN.search(stock_label)
        if not match:
            ignored_entries.append(entry)
            continue
        code = match.group(1).strip().upper()
        name = stock_label.split("(", 1)[0].strip()
        try:
            shares = int(str(entry.get("股數", "0")).replace(",", ""))
        except ValueError:
            ignored_entries.append(entry)
            continue

        item = stocks.setdefault(code, {
            "stock_code": code,
            "stock_name": name,
            "opening_shares": 0,
            "current_shares": 0,
            "buys_after_as_of": 0,
            "sells_after_as_of": 0,
        })
        if not item["stock_name"]:
            item["stock_name"] = name
        if "買" in trade_type:
            item["buys_after_as_of"] += shares
            item["opening_shares"] -= shares
        else:
            item["sells_after_as_of"] += shares
            item["opening_shares"] += shares

    positions = [item for item in stocks.values() if item["opening_shares"]]
    positions.sort(key=lambda item: item["stock_code"])
    return {
        "as_of": as_of,
        "method": "current_shares + sells_after_as_of - buys_after_as_of",
        "cost_basis_available": False,
        "cost_basis_note": "此端點反推數量；精確期初成本需要更早成交或指定日庫存成本資料。",
        "count": len(positions),
        "positions": positions,
        "ignored_entry_count": len(ignored_entries),
    }
