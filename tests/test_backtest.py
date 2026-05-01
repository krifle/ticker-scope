from __future__ import annotations

from unittest.mock import patch
import unittest

import pandas as pd

from ticker_scope.modeling import backtest


class BacktestTests(unittest.TestCase):
    def test_score_forecast_calculates_error_metrics_and_coverage(self) -> None:
        result = pd.DataFrame(
            {
                "y": [100.0, 110.0, 120.0],
                "yhat": [90.0, 115.0, 130.0],
                "yhat_lower": [80.0, 108.0, 125.0],
                "yhat_upper": [105.0, 118.0, 135.0],
            }
        )

        metrics = backtest.score_forecast(result)

        self.assertAlmostEqual(metrics["mae"], 25.0 / 3.0)
        self.assertAlmostEqual(metrics["rmse"], (225.0 / 3.0) ** 0.5)
        self.assertAlmostEqual(
            metrics["mape"],
            ((10.0 / 100.0) + (5.0 / 110.0) + (10.0 / 120.0)) / 3.0 * 100,
        )
        self.assertAlmostEqual(metrics["coverage"], 200.0 / 3.0)

    def test_holdout_metrics_frame_describes_split_window(self) -> None:
        prophet_df = pd.DataFrame(
            {
                "ds": pd.date_range("2024-01-01", periods=40, freq="D"),
                "y": [float(value) for value in range(40)],
            }
        )

        metrics = {"mae": 1.0, "rmse": 2.0, "mape": 3.0, "coverage": 4.0}
        frame = backtest.make_holdout_metrics_frame(
            prophet_df,
            metrics,
            train_ratio=0.75,
        )

        row = frame.iloc[0]
        self.assertTrue(pd.isna(row["horizon_days"]))
        self.assertEqual(row["cutoff_date"], pd.Timestamp("2024-01-30"))
        self.assertEqual(row["train_start_date"], pd.Timestamp("2024-01-01"))
        self.assertEqual(row["train_end_date"], pd.Timestamp("2024-01-30"))
        self.assertEqual(row["test_start_date"], pd.Timestamp("2024-01-31"))
        self.assertEqual(row["test_end_date"], pd.Timestamp("2024-02-09"))
        self.assertEqual(int(row["test_rows"]), 10)

    def test_rolling_backtest_scores_multiple_horizons(self) -> None:
        prophet_df = pd.DataFrame(
            {
                "ds": pd.bdate_range("2024-01-02", periods=120),
                "y": [float(value) for value in range(120)],
            }
        )
        value_by_date = dict(zip(prophet_df["ds"], prophet_df["y"], strict=True))

        def fake_predict_dates(train_df, dates, holidays=None, interval_width=0.8):
            forecast_dates = pd.to_datetime(dates)
            yhat = [value_by_date[item] for item in forecast_dates]
            return pd.DataFrame(
                {
                    "ds": forecast_dates,
                    "yhat": yhat,
                    "yhat_lower": [value - 1 for value in yhat],
                    "yhat_upper": [value + 1 for value in yhat],
                }
            )

        with patch.object(backtest, "predict_dates", side_effect=fake_predict_dates):
            result, metrics = backtest.run_rolling_backtest(
                prophet_df,
                horizons_days=[7, 30],
                rolling_windows=3,
                min_train_rows=40,
            )

        summary = backtest.summarize_rolling_metrics(metrics)

        self.assertFalse(result.empty)
        self.assertEqual(set(metrics["horizon_days"]), {7, 30})
        self.assertEqual(set(summary["horizon_days"]), {7, 30})
        self.assertEqual(float(summary["mape"].max()), 0.0)
        self.assertEqual(float(summary["coverage"].min()), 100.0)


if __name__ == "__main__":
    unittest.main()
