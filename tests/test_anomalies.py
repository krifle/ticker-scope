from __future__ import annotations

import unittest

import pandas as pd

from ticker_scope.modeling.anomalies import detect_interval_anomalies


class AnomalyTests(unittest.TestCase):
    def test_interval_anomalies_include_explainable_columns(self) -> None:
        actual = pd.DataFrame(
            {
                "ds": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "y": [12.0, 6.0],
            }
        )
        forecast = pd.DataFrame(
            {
                "ds": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "yhat": [10.0, 10.0],
                "yhat_lower": [8.0, 8.0],
                "yhat_upper": [11.0, 12.0],
            }
        )

        result = detect_interval_anomalies(actual, forecast)

        self.assertTrue(result["is_anomaly"].all())
        self.assertEqual(list(result["bound_exceeded"]), ["upper", "lower"])
        self.assertEqual(list(result["expected_range"]), ["8.00 ~ 11.00", "8.00 ~ 12.00"])
        self.assertIn("upper forecast bound", result.iloc[0]["explanation"])
        self.assertIn("lower forecast bound", result.iloc[1]["explanation"])


if __name__ == "__main__":
    unittest.main()
