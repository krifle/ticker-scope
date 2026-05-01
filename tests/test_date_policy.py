from __future__ import annotations

import unittest

import pandas as pd

from ticker_scope.date_policy import (
    CALENDAR_DAY,
    US_STOCK_MARKET,
    expected_dates_between,
    make_future_dataframe,
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


if __name__ == "__main__":
    unittest.main()
