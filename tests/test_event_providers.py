from __future__ import annotations

import unittest
from unittest.mock import Mock

import pandas as pd

from ticker_scope.events.providers import (
    AlphaVantageEarningsClient,
    EarningsCalendarRequest,
    EventProviderRateLimitError,
    normalize_alpha_vantage_earnings_csv,
)


class EventProviderTests(unittest.TestCase):
    def test_alpha_vantage_csv_is_normalized_to_events(self) -> None:
        csv_text = "\n".join(
            [
                "symbol,name,reportDate,fiscalDateEnding,estimate,currency",
                "TSLA,Tesla Inc,2026-07-22,2026-06-30,0.62,USD",
                "AAPL,Apple Inc,2026-07-30,2026-06-30,1.50,USD",
            ]
        )

        events = normalize_alpha_vantage_earnings_csv(
            csv_text,
            requested_symbol="TSLA",
        )

        self.assertEqual(len(events), 1)
        row = events.iloc[0]
        self.assertEqual(row["ticker"], "TSLA")
        self.assertEqual(row["event_date"].isoformat(), "2026-07-22")
        self.assertEqual(row["category"], "earnings")
        self.assertEqual(row["source"], "alpha_vantage_earnings")
        self.assertEqual(int(row["lower_window"]), -1)
        self.assertEqual(int(row["upper_window"]), 1)
        self.assertIn("Tesla Inc", row["notes"])

    def test_alpha_vantage_limit_message_raises_rate_limit_error(self) -> None:
        with self.assertRaises(EventProviderRateLimitError):
            normalize_alpha_vantage_earnings_csv(
                "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."
            )

    def test_client_builds_expected_request(self) -> None:
        response = Mock()
        response.status_code = 200
        response.text = "symbol,name,reportDate\nTSLA,Tesla Inc,2026-07-22\n"
        response.raise_for_status = Mock()
        session = Mock()
        session.get.return_value = response

        client = AlphaVantageEarningsClient(session=session)
        events = client.fetch_earnings_calendar(
            EarningsCalendarRequest(
                symbol="tsla",
                horizon="6month",
                api_key="demo",
            )
        )

        session.get.assert_called_once()
        params = session.get.call_args.kwargs["params"]
        self.assertEqual(params["function"], "EARNINGS_CALENDAR")
        self.assertEqual(params["symbol"], "TSLA")
        self.assertEqual(params["horizon"], "6month")
        self.assertEqual(params["apikey"], "demo")
        self.assertEqual(events["ticker"].tolist(), ["TSLA"])


if __name__ == "__main__":
    unittest.main()
