"""將站方以 Big5 HTML 偽裝的 XLS 轉成可交換的 UTF-8 格式。"""

import csv
import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path


GROUPS = [
    ("depository", 1),
    ("odd_lot", 7),
    ("margin", 13),
    ("short", 19),
]
FIELDS = ["previous", "buy_order", "buy_filled", "sell_order", "sell_filled", "current"]
GROUP_UNITS = {
    "depository": "lot",
    "odd_lot": "share",
    "margin": "lot",
    "short": "lot",
}


def enrich_inventory_item(item: dict) -> dict:
    """補上單位與股數換算，避免把零股 500 誤認為 500 張。"""
    for group, unit in GROUP_UNITS.items():
        values = item.get(group)
        if isinstance(values, dict):
            values["unit"] = unit

    def current(group):
        value = item.get(group, {}).get("current", 0)
        return value if isinstance(value, int) else 0

    cash_shares = current("depository") * 1000 + current("odd_lot")
    margin_shares = current("margin") * 1000
    short_shares = current("short") * 1000
    item["share_summary"] = {
        "cash_shares": cash_shares,
        "margin_shares": margin_shares,
        "short_shares": short_shares,
        "long_shares": cash_shares + margin_shares,
        "net_shares": cash_shares + margin_shares - short_shares,
        "unit": "share",
    }
    return item


def inventory_item_from_values(values: list[str]):
    """將彙總庫存的一列 25 欄資料轉成穩定結構。"""
    if len(values) != 25:
        return None

    match = re.search(r"\(([^()]+)\)\s*$", values[0])
    if not match:
        return None

    def number(value):
        value = value.strip().replace(",", "")
        try:
            return int(value) if value else 0
        except ValueError:
            return value

    code = match.group(1)
    name = re.sub(r"^\*|\*?\([^()]+\)\s*$", "", values[0]).strip("*")
    item = {"code": code, "name": name}
    for group, start in GROUPS:
        item[group] = {
            field: number(values[start + offset])
            for offset, field in enumerate(FIELDS)
        }
    return enrich_inventory_item(item)


class _TableDataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def close(self):
        super().close()
        if self._row:
            self.rows.append(self._row)
            self._row = None


def _decode_export(raw: bytes) -> str:
    """優先依站方宣告解 Big5，並容忍少數 CP950 擴充字元。"""
    head = raw[:1024].decode("ascii", errors="ignore")
    match = re.search(r"charset\s*=\s*['\"]?([\w-]+)", head, re.IGNORECASE)
    declared = match.group(1).lower() if match else ""
    encodings = ["cp950", "big5"] if declared in {"big5", "cp950"} else ["utf-8-sig", "cp950", "big5"]
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError("無法辨識庫存 XLS 的文字編碼")


def convert_inventory_xls(filepath: Path) -> tuple[Path, Path, list[dict]]:
    """保留原始 XLS，另存 UTF-8 JSON 與可由 Excel 正確開啟的 CSV。"""
    filepath = Path(filepath)
    parser = _TableDataParser()
    parser.feed(_decode_export(filepath.read_bytes()))
    parser.close()

    positions = {}
    for values in parser.rows:
        item = inventory_item_from_values(values)
        if item:
            positions[item["code"]] = item
    data = list(positions.values())
    if not data:
        raise ValueError("XLS 中找不到 25 欄的彙總庫存資料")

    json_path = filepath.with_name(f"{filepath.stem}_utf8.json")
    csv_path = filepath.with_name(f"{filepath.stem}_utf8.csv")
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", filepath.stem)
    result = {
        "date": date_match.group(1) if date_match else date.today().isoformat(),
        "source": "xls",
        "positions": data,
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    columns = ["code", "name"] + [
        f"{group}.{field}" for group, _ in GROUPS for field in FIELDS
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        for item in data:
            row = {"code": item["code"], "name": item["name"]}
            for group, _ in GROUPS:
                for field in FIELDS:
                    row[f"{group}.{field}"] = item[group][field]
            writer.writerow(row)

    return json_path, csv_path, data
