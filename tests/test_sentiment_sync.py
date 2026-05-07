from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from ticker_scope.data.database import get_connection
from ticker_scope.data.repositories import get_fear_greed_history, get_recent_sync_runs
from ticker_scope.sentiment.sync import sync_fear_greed_index


class FakeFearGreedClient:
    def __init__(self, history: pd.DataFrame) -> None:
        self.history = history
        self.calls = 0

    def fetch_history(self, last: str = "1y") -> pd.DataFrame:
        self.calls += 1
        return self.history


class SentimentSyncTests(unittest.TestCase):
    def test_sync_fear_greed_index_stores_history_then_uses_recent_success(self) -> None:
        client = FakeFearGreedClient(
            pd.DataFrame(
                {
                    "index_date": ["2024-01-02", "2024-01-03"],
                    "value": [24, 52],
                    "classification": ["Extreme Fear", "Neutral"],
                }
            )
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            with patch.dict("os.environ", {"TICKER_SCOPE_DB_PATH": str(db_path)}):
                first = sync_fear_greed_index(client=client)
                second = sync_fear_greed_index(client=client)

                with get_connection(db_path) as connection:
                    history = get_fear_greed_history(connection)
                    sync_runs = get_recent_sync_runs(
                        connection,
                        ticker="MARKET",
                        limit=10,
                    )

        self.assertEqual(client.calls, 1)
        self.assertEqual(first.stored_rows, 2)
        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(len(history), 2)
        self.assertEqual(sync_runs["status"].tolist(), ["skipped", "success"])


if __name__ == "__main__":
    unittest.main()
