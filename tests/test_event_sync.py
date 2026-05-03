from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from ticker_scope.data.database import get_connection, init_database
from ticker_scope.data.repositories import add_event, get_recent_sync_runs, list_events
from ticker_scope.events.sync import merge_external_events, sync_earnings_events


class FakeEarningsClient:
    def __init__(self, events: pd.DataFrame) -> None:
        self.events = events
        self.calls = 0

    def fetch_earnings_calendar(self, request) -> pd.DataFrame:
        self.calls += 1
        return self.events


class EventSyncTests(unittest.TestCase):
    def test_merge_external_events_skips_manual_duplicate(self) -> None:
        external_events = pd.DataFrame(
            [
                {
                    "ticker": "TSLA",
                    "event_date": date(2026, 7, 22),
                    "name": "TSLA earnings",
                    "category": "earnings",
                    "lower_window": -1,
                    "upper_window": 1,
                    "source": "alpha_vantage_earnings",
                    "notes": "Provider: Alpha Vantage",
                },
                {
                    "ticker": "TSLA",
                    "event_date": date(2026, 10, 21),
                    "name": "TSLA earnings",
                    "category": "earnings",
                    "lower_window": -1,
                    "upper_window": 1,
                    "source": "alpha_vantage_earnings",
                    "notes": "Provider: Alpha Vantage",
                },
            ]
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)
            with get_connection(db_path) as connection:
                add_event(
                    connection,
                    name="Manual TSLA earnings",
                    event_date=date(2026, 7, 22),
                    category="earnings",
                    ticker="TSLA",
                    source="manual",
                )
                inserted, skipped = merge_external_events(connection, external_events)
                connection.commit()
                events = list_events(connection, ticker="TSLA", include_global=False)

        self.assertEqual(inserted, 1)
        self.assertEqual(skipped, 1)
        self.assertEqual(len(events), 2)
        self.assertEqual(set(events["source"]), {"manual", "alpha_vantage_earnings"})

    def test_sync_earnings_events_uses_recent_success_as_rate_limit_cache(self) -> None:
        external_events = pd.DataFrame(
            [
                {
                    "ticker": "TSLA",
                    "event_date": date(2026, 7, 22),
                    "name": "TSLA earnings",
                    "category": "earnings",
                    "lower_window": -1,
                    "upper_window": 1,
                    "source": "alpha_vantage_earnings",
                    "notes": "Provider: Alpha Vantage",
                }
            ]
        )
        client = FakeEarningsClient(external_events)

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            with patch.dict("os.environ", {"TICKER_SCOPE_DB_PATH": str(db_path)}):
                first = sync_earnings_events(
                    "TSLA",
                    api_key="demo",
                    client=client,
                )
                second = sync_earnings_events(
                    "TSLA",
                    api_key="demo",
                    client=client,
                )

                with get_connection(db_path) as connection:
                    events = list_events(connection, ticker="TSLA", include_global=False)
                    sync_runs = get_recent_sync_runs(connection, ticker="TSLA", limit=10)

        self.assertEqual(client.calls, 1)
        self.assertEqual(first.inserted_rows, 1)
        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(second.inserted_rows, 0)
        self.assertEqual(len(events), 1)
        self.assertEqual(sync_runs["status"].tolist(), ["skipped", "success"])

    def test_sync_earnings_events_cache_is_scoped_by_horizon(self) -> None:
        external_events = pd.DataFrame(
            [
                {
                    "ticker": "TSLA",
                    "event_date": date(2026, 7, 22),
                    "name": "TSLA earnings",
                    "category": "earnings",
                    "lower_window": -1,
                    "upper_window": 1,
                    "source": "alpha_vantage_earnings",
                    "notes": "Provider: Alpha Vantage",
                }
            ]
        )
        client = FakeEarningsClient(external_events)

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            with patch.dict("os.environ", {"TICKER_SCOPE_DB_PATH": str(db_path)}):
                first = sync_earnings_events(
                    "TSLA",
                    horizon="3month",
                    api_key="demo",
                    client=client,
                )
                second = sync_earnings_events(
                    "TSLA",
                    horizon="6month",
                    api_key="demo",
                    client=client,
                )
                third = sync_earnings_events(
                    "TSLA",
                    horizon="6month",
                    api_key="demo",
                    client=client,
                )

        self.assertEqual(client.calls, 2)
        self.assertFalse(first.from_cache)
        self.assertFalse(second.from_cache)
        self.assertTrue(third.from_cache)


if __name__ == "__main__":
    unittest.main()
