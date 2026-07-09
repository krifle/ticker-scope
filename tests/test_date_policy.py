from __future__ import annotations

import unittest

import pandas as pd

from ticker_scope.date_policy import (
    AUTO_BY_TICKER,
    CALENDAR_DAY,
    KOREA_STOCK_MARKET,
    US_STOCK_MARKET,
    expected_dates_between,
    make_future_dataframe,
    resolve_date_policy_for_symbol,
)


class DatePolicyTests(unittest.TestCase):
    def test_us_stock_future_dates_skip_weekends_and_nyse_holidays(self) -> None:
        prophet_df = pd.DataFrame(
            {
                "ds": pd.to_datetime(["2024-03-27", "2024-03-28"]),
                "y": [10.0, 11.0],
            }
        )

        future = make_future_dataframe(
            prophet_df,
            periods=3,
            date_policy=US_STOCK_MARKET,
            include_history=False,
        )

        self.assertEqual(
            [item.date().isoformat() for item in future["ds"]],
            ["2024-04-01", "2024-04-02", "2024-04-03"],
        )

    def test_calendar_future_dates_keep_every_day(self) -> None:
        prophet_df = pd.DataFrame(
            {
                "ds": pd.to_datetime(["2024-03-27", "2024-03-28"]),
                "y": [10.0, 11.0],
            }
        )

        future = make_future_dataframe(
            prophet_df,
            periods=3,
            date_policy=CALENDAR_DAY,
            include_history=False,
        )

        self.assertEqual(
            [item.date().isoformat() for item in future["ds"]],
            ["2024-03-29", "2024-03-30", "2024-03-31"],
        )

    def test_expected_us_stock_dates_skip_good_friday(self) -> None:
        expected = expected_dates_between(
            "2024-03-28",
            "2024-04-01",
            date_policy=US_STOCK_MARKET,
        )

        self.assertEqual(
            [item.isoformat() for item in expected],
            ["2024-03-28", "2024-04-01"],
        )

    def test_korea_stock_future_dates_skip_korean_market_holidays(self) -> None:
        prophet_df = pd.DataFrame(
            {
                "ds": pd.to_datetime(["2025-04-29", "2025-04-30"]),
                "y": [10.0, 11.0],
            }
        )

        future = make_future_dataframe(
            prophet_df,
            periods=3,
            date_policy=KOREA_STOCK_MARKET,
            include_history=False,
        )

        self.assertEqual(
            [item.date().isoformat() for item in future["ds"]],
            ["2025-05-02", "2025-05-07", "2025-05-08"],
        )

    def test_auto_policy_resolves_korean_yahoo_suffixes(self) -> None:
        self.assertEqual(
            resolve_date_policy_for_symbol("034020.KS", AUTO_BY_TICKER),
            KOREA_STOCK_MARKET,
        )
        self.assertEqual(
            resolve_date_policy_for_symbol("123456.KQ", AUTO_BY_TICKER),
            KOREA_STOCK_MARKET,
        )
        self.assertEqual(
            resolve_date_policy_for_symbol("TSLA", AUTO_BY_TICKER),
            US_STOCK_MARKET,
        )

    def test_auto_policy_requires_symbol_context_for_date_generation(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a ticker symbol"):
            expected_dates_between(
                "2025-05-01",
                "2025-05-02",
                date_policy=AUTO_BY_TICKER,
            )


if __name__ == "__main__":
    unittest.main()
