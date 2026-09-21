import unittest
from datetime import date

from entrust.portfolio import aggregate_statements, calculate_opening_inventory, history_windows


class PortfolioTest(unittest.TestCase):
    def test_history_windows_split_long_range_without_overlap(self):
        result = history_windows(date(2025, 9, 1), date(2026, 9, 21))

        self.assertEqual(result[0], (date(2025, 9, 1), date(2026, 3, 3)))
        self.assertEqual(result[1][0], date(2026, 3, 4))
        self.assertEqual(result[-1][1], date(2026, 9, 21))

    def test_aggregate_statements_combines_and_sorts_entries(self):
        chunks = [
            {"date_from": "2025-09-01", "date_to": "2026-02-28", "count": 1,
             "entries": [{"成交日期": "2025/10/01"}]},
            {"date_from": "2026-03-01", "date_to": "2026-09-21", "count": 1,
             "entries": [{"成交日期": "2026/06/01"}]},
        ]

        result = aggregate_statements(chunks, "2025-09-01", "2026-09-21")

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["entries"][0]["成交日期"], "2026/06/01")
        self.assertEqual(result["chunk_count"], 2)

    def test_calculate_opening_inventory_reverses_cash_trades(self):
        current = [{
            "code": "0050",
            "name": "元大台灣50",
            "share_summary": {"cash_shares": 178000},
        }]
        entries = [
            {"類別": "現股\n買進", "股票": "元大台灣50\n(0050)", "股數": "3,000"},
            {"類別": "現股\n賣出", "股票": "聯發科\n(2454)", "股數": "1,400"},
            {"類別": "融資\n買進", "股票": "台積電\n(2330)", "股數": "1,000"},
        ]

        result = calculate_opening_inventory(current, entries, "2025-09-01")
        by_code = {item["stock_code"]: item for item in result["positions"]}

        self.assertEqual(by_code["0050"]["opening_shares"], 175000)
        self.assertEqual(by_code["2454"]["opening_shares"], 1400)
        self.assertEqual(result["ignored_entry_count"], 1)


if __name__ == "__main__":
    unittest.main()
