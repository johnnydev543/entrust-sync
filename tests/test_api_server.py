import unittest
from datetime import date, timedelta

from fastapi import HTTPException

from api_server import _validate_history_range, _validate_stock_code


class ApiValidationTest(unittest.TestCase):
    def test_stock_code_is_optional(self):
        self.assertIsNone(_validate_stock_code(None))
        self.assertIsNone(_validate_stock_code("  "))

    def test_stock_code_is_normalized(self):
        self.assertEqual(_validate_stock_code(" 00631l "), "00631L")

    def test_stock_code_rejects_symbols(self):
        with self.assertRaises(HTTPException):
            _validate_stock_code("2330;drop")

    def test_history_range_accepts_six_month_window(self):
        end = date.today()
        start = end - timedelta(days=180)
        self.assertEqual(
            _validate_history_range(start.isoformat(), end.isoformat()),
            (start.isoformat(), end.isoformat()),
        )

    def test_history_range_rejects_too_long_window(self):
        end = date.today()
        start = end - timedelta(days=184)
        with self.assertRaises(HTTPException):
            _validate_history_range(start.isoformat(), end.isoformat())


if __name__ == "__main__":
    unittest.main()
