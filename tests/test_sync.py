from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from ticker_scope.data import sync
from ticker_scope.data.database import get_connection, init_database
from ticker_scope.data.market_data import MarketDataRequest
from ticker_scope.data.repositories import get_recent_sync_runs


class FixedDate(date):
    @classmethod
    def today(cls) -> date:
        return cls(2024, 1, 5)


class KoreanHolidayWeekDate(date):
    @classmethod
    def today(cls) -> date:
        return cls(2025, 10, 11)


class SyncTests(unittest.TestCase):
    def test_build_fetch_requests_merges_overlapping_ranges(self) -> None:
        requests = sync._build_fetch_requests(
            symbol="TSLA",
            period="5y",
            interval="1d",
            auto_adjust=True,
            requested_start=date(2024, 1, 1),
            first_stored=date(2024, 1, 10),
            last_stored=date(2024, 1, 20),
            today=date(2024, 1, 25),
            force_refresh=False,
            missing_ranges=[
                (date(2024, 1, 11), date(2024, 1, 16), 6),
                (date(2024, 1, 16), date(2024, 1, 18), 3),
            ],
        )

        self.assertEqual(
            [(request.start, request.end) for request in requests],
            [
                (date(2024, 1, 1), date(2024, 1, 19)),
                (date(2024, 1, 20), date(2024, 1, 26)),
            ],
        )

    def test_sync_price_history_stores_first_download_then_uses_cache(self) -> None:
        downloaded = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
                "Open": [9.0, 10.0, 11.0, 12.0],
                "High": [10.0, 11.0, 12.0, 13.0],
                "Low": [8.0, 9.0, 10.0, 11.0],
                "Close": [10.0, 11.0, 12.0, 13.0],
                "Volume": [100, 200, 300, 400],
                "Symbol": ["TSLA"] * 4,
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)

            with patch.dict("os.environ", {"TICKER_SCOPE_DB_PATH": str(db_path)}), patch.object(
                sync,
                "date",
                FixedDate,
            ), patch.object(sync, "load_price_history", return_value=downloaded) as load_price_history:
                first_result = sync.sync_price_history("tsla", period="max")
                second_result = sync.sync_price_history("TSLA", period="max")

            self.assertEqual(load_price_history.call_count, 1)
            self.assertEqual(first_result.fetched_rows, 4)
            self.assertEqual(first_result.stored_rows, 4)
            self.assertFalse(first_result.from_cache)
            self.assertEqual(len(second_result.history), 4)
            self.assertEqual(second_result.fetched_rows, 0)
            self.assertTrue(second_result.from_cache)
            self.assertEqual(second_result.message, "cache hit")

            with get_connection(db_path) as connection:
                sync_runs = get_recent_sync_runs(connection, ticker="TSLA", limit=10)

            self.assertEqual(len(sync_runs), 2)
            self.assertEqual(sync_runs["status"].tolist(), ["success", "success"])
            self.assertEqual(sync_runs.iloc[0]["message"], "cache hit")

    def test_sync_uses_korean_market_calendar_for_missing_ranges(self) -> None:
        stored_history = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-10-02", "2025-10-10"]),
                "Close": [10.0, 11.0],
                "Volume": [100, 200],
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)
            with get_connection(db_path) as connection:
                sync.upsert_daily_prices(connection, "034020.KS", stored_history)
                connection.commit()

            with patch.dict("os.environ", {"TICKER_SCOPE_DB_PATH": str(db_path)}), patch.object(
                sync,
                "date",
                KoreanHolidayWeekDate,
            ), patch.object(sync, "load_price_history") as load_price_history:
                result = sync.sync_price_history("034020.KS", period="max")

            load_price_history.assert_not_called()
            self.assertTrue(result.from_cache)
            self.assertEqual(result.message, "cache hit")
            self.assertEqual(len(result.history), 2)

    def test_merge_fetch_requests_keeps_period_request_unmerged(self) -> None:
        period_request = MarketDataRequest(symbol="TSLA", period="max", start=None, end=None)
        dated_request = MarketDataRequest(
            symbol="TSLA",
            period="5y",
            start=date(2024, 1, 1),
            end=date(2024, 1, 5),
        )

        result = sync._merge_fetch_requests(
            [period_request, dated_request],
            symbol="TSLA",
            period="max",
            interval="1d",
            auto_adjust=True,
        )

        self.assertEqual(result, [period_request, dated_request])


if __name__ == "__main__":
    unittest.main()
