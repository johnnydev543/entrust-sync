import json
import tempfile
import unittest
from pathlib import Path

from entrust.api_data import (
    DataNotFoundError,
    available_dates,
    get_holdings,
    get_transaction_history,
    get_transactions,
)


class ApiDataTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        (self.output_dir / "aggregate_inventory_2026-09-17.json").write_text(
            json.dumps({"date": "2026-09-17", "positions": [{"code": "0050", "name": "ETF"}]}),
            encoding="utf-8",
        )
        for sync_date, code in [("2026-09-17", "2330"), ("2026-09-18", "0050")]:
            (self.output_dir / f"transactions_{sync_date}.json").write_text(
                json.dumps({
                    "date": sync_date,
                    "tables": [{"table_index": 2, "source": "iframe_1", "data": [{"代號": code}]}],
                }),
                encoding="utf-8",
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_holdings_defaults_to_latest(self):
        result = get_holdings(output_dir=self.output_dir)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["positions"][0]["code"], "0050")

    def test_holdings_adds_explicit_units_and_share_summary(self):
        position = {
            "code": "8299",
            "name": "群聯",
            "depository": {"current": 0},
            "odd_lot": {"current": 500},
            "margin": {"current": 0},
            "short": {"current": 0},
        }
        (self.output_dir / "aggregate_inventory_2026-09-17.json").write_text(
            json.dumps({"date": "2026-09-17", "positions": [position]}),
            encoding="utf-8",
        )

        result = get_holdings(output_dir=self.output_dir)
        item = result["positions"][0]

        self.assertEqual(item["depository"]["unit"], "lot")
        self.assertEqual(item["odd_lot"]["unit"], "share")
        self.assertEqual(item["share_summary"]["long_shares"], 500)

    def test_transactions_are_flattened(self):
        result = get_transactions("2026-09-18", self.output_dir)
        self.assertEqual(result["transactions"][0]["data"]["代號"], "0050")

    def test_history_filters_and_limits(self):
        result = get_transaction_history("2026-09-17", "2026-09-18", 1, self.output_dir)
        self.assertEqual(result["total"], 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["transactions"][0]["date"], "2026-09-18")

    def test_dates_and_missing_data(self):
        self.assertEqual(available_dates(self.output_dir)["transactions"], ["2026-09-18", "2026-09-17"])
        with self.assertRaises(DataNotFoundError):
            get_transactions("2026-09-16", self.output_dir)

    def test_invalid_date_is_rejected(self):
        with self.assertRaises(ValueError):
            get_transactions("../../.env", self.output_dir)


if __name__ == "__main__":
    unittest.main()
