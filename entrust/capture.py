"""表格擷取與彙總庫存匯出（三支腳本中逐字相同的副本收斂）。"""

import json
from datetime import date
from pathlib import Path

from inventory_export import convert_inventory_xls, inventory_item_from_values

from entrust.config import DEFAULT_TIMEOUT, OUTPUT_DIR


def capture_all_tables(page) -> list[dict]:
    """抓取所有表格（含 iframe 和其他頁面）"""
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
                "table_index": t_idx, "headers": headers,
                "row_count": len(data_rows), "data": data_rows, "source": "main",
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
                        "table_index": t_idx, "headers": headers,
                        "row_count": len(data_rows), "data": data_rows,
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
                with page.expect_download(timeout=DEFAULT_TIMEOUT) as download_info:
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


def save_step(step_name: str, page, tables_data: list[dict], alerts: list[dict]):
    """儲存單一步驟的 url、title、表格與 alert 紀錄。

    alerts 由呼叫端傳入該步驟的 alert_log.copy()，避免模組狀態耦合。
    """
    today = date.today().isoformat()
    output_file = OUTPUT_DIR / f"{step_name}_{today}.json"

    result = {
        "step": step_name,
        "date": today,
        "page_url": page.url,
        "page_title": page.title(),
        "tables": tables_data,
        "alerts": alerts,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"   💾 已存: {output_file}")
    return output_file
