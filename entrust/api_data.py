"""讀取同步結果，提供 API 使用的穩定資料結構。"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from entrust.config import OUTPUT_DIR
from inventory_export import enrich_inventory_item


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DataNotFoundError(FileNotFoundError):
    """找不到指定同步資料。"""


def validate_date(value: str) -> str:
    """驗證 API 日期參數，避免日期格式模糊或路徑穿越。"""
    if not DATE_PATTERN.fullmatch(value):
        raise ValueError("日期格式必須是 YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("日期不是有效日期") from exc
    return value


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataNotFoundError(f"無法讀取同步資料：{path.name}") from exc
    if not isinstance(data, dict):
        raise DataNotFoundError(f"同步資料格式錯誤：{path.name}")
    return data


def _dated_files(prefix: str, output_dir: Path) -> dict[str, Path]:
    files = {}
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d{{4}}-\d{{2}}-\d{{2}})\.json$")
    for path in output_dir.glob(f"{prefix}_*.json"):
        match = pattern.fullmatch(path.name)
        if match:
            files[match.group(1)] = path
    return files


def available_dates(output_dir: Path = OUTPUT_DIR) -> dict[str, list[str]]:
    """列出各類同步結果目前可查詢的日期。"""
    return {
        "holdings": sorted(_dated_files("aggregate_inventory", output_dir), reverse=True),
        "transactions": sorted(_dated_files("transactions", output_dir), reverse=True),
    }


def get_holdings(sync_date: Optional[str] = None, output_dir: Path = OUTPUT_DIR) -> dict:
    """讀取指定日期或最近一次的彙總持股。"""
    files = _dated_files("aggregate_inventory", output_dir)
    selected_date = validate_date(sync_date) if sync_date else (max(files) if files else None)
    if not selected_date or selected_date not in files:
        label = selected_date or "任何日期"
        raise DataNotFoundError(f"找不到 {label} 的持股同步資料")

    payload = _read_json(files[selected_date])
    positions = payload.get("positions")
    if not isinstance(positions, list):
        raise DataNotFoundError(f"持股同步資料格式錯誤：{files[selected_date].name}")
    positions = [enrich_inventory_item(dict(position)) for position in positions]
    return {
        "date": payload.get("date", selected_date),
        "source": payload.get("source", "華南永昌證券"),
        "market_value": payload.get("market_value"),
        "count": len(positions),
        "positions": positions,
    }


def _transaction_rows(payload: dict, sync_date: str) -> list[dict]:
    rows = []
    for table in payload.get("tables", []):
        if not isinstance(table, dict):
            continue
        for row in table.get("data", []):
            if not isinstance(row, dict) or not any(str(value).strip() for value in row.values()):
                continue
            rows.append({
                "date": sync_date,
                "table_index": table.get("table_index"),
                "source": table.get("source", "main"),
                "data": row,
            })
    return rows


def get_transactions(sync_date: str, output_dir: Path = OUTPUT_DIR) -> dict:
    """讀取並攤平單日交易表格。"""
    sync_date = validate_date(sync_date)
    path = _dated_files("transactions", output_dir).get(sync_date)
    if not path:
        raise DataNotFoundError(f"找不到 {sync_date} 的交易同步資料")
    payload = _read_json(path)
    rows = _transaction_rows(payload, sync_date)
    return {
        "date": payload.get("date", sync_date),
        "source": payload.get("source", "華南永昌證券"),
        "count": len(rows),
        "transactions": rows,
    }


def get_transaction_history(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 1000,
    output_dir: Path = OUTPUT_DIR,
) -> dict:
    """合併日期區間內的交易同步資料，日期由新到舊。"""
    if date_from:
        date_from = validate_date(date_from)
    if date_to:
        date_to = validate_date(date_to)
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from 不可晚於 date_to")

    rows = []
    matched_dates = []
    files = _dated_files("transactions", output_dir)
    for sync_date in sorted(files, reverse=True):
        if date_from and sync_date < date_from:
            continue
        if date_to and sync_date > date_to:
            continue
        matched_dates.append(sync_date)
        rows.extend(_transaction_rows(_read_json(files[sync_date]), sync_date))

    total = len(rows)
    return {
        "date_from": date_from,
        "date_to": date_to,
        "available_dates": matched_dates,
        "total": total,
        "count": min(total, limit),
        "truncated": total > limit,
        "transactions": rows[:limit],
    }
