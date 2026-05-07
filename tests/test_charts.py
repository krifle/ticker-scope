from __future__ import annotations

import unittest

import pandas as pd

from ticker_scope.ui.charts import (
    make_components_chart,
    make_forecast_chart,
    make_multi_anomaly_chart,
    make_multi_metric_bar_chart,
)


class ChartTests(unittest.TestCase):
    def test_forecast_chart_displays_visible_events(self) -> None:
        actual = pd.DataFrame(
            {
                "ds": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "y": [10.0, 11.0],
            }
        )
        forecast = pd.DataFrame(
            {
                "ds": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
                "yhat": [10.0, 10.5, 11.0],
                "yhat_lower": [9.0, 9.5, 10.0],
                "yhat_upper": [11.0, 11.5, 12.0],
            }
        )
        events = pd.DataFrame(
            {
                "name": ["Earnings", "Outside range"],
                "event_date": ["2024-01-03", "2024-02-01"],
                "category": ["earnings", "manual"],
                "ticker": ["TSLA", "TSLA"],
                "lower_window": [-1, 0],
                "upper_window": [1, 0],
            }
        )

        fig = make_forecast_chart(actual, forecast, events=events)
        event_traces = [trace for trace in fig.data if trace.name == "Events"]

        self.assertEqual(len(event_traces), 1)
        self.assertEqual(len(event_traces[0].x), 1)
        self.assertIn("Earnings", event_traces[0].text[0])

    def test_forecast_chart_adds_fear_greed_subchart(self) -> None:
        actual = pd.DataFrame(
            {
                "ds": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "y": [10.0, 11.0],
            }
        )
        forecast = pd.DataFrame(
            {
                "ds": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "yhat": [10.0, 10.5],
                "yhat_lower": [9.0, 9.5],
                "yhat_upper": [11.0, 11.5],
            }
        )
        fear_greed = pd.DataFrame(
            {
                "index_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "value": [24, 52],
                "classification": ["Extreme Fear", "Neutral"],
                "source": ["cnn_api", "manual"],
            }
        )

        fig = make_forecast_chart(actual, forecast, fear_greed=fear_greed)
        sentiment_traces = [trace for trace in fig.data if trace.name == "Fear & Greed"]

        self.assertEqual(len(sentiment_traces), 1)
        self.assertEqual(list(sentiment_traces[0].y), [24, 52])
        self.assertEqual(fig.layout.yaxis2.range, (0, 100))
        self.assertGreaterEqual(len(fig.layout.shapes), 5)

    def test_multi_ticker_charts_render_summary_bars(self) -> None:
        summary = pd.DataFrame(
            {
                "ticker": ["TSLA", "AAPL"],
                "mape": [12.5, 5.1],
                "anomaly_rate_pct": [3.0, 1.5],
                "anomaly_count": [9, 4],
            }
        )

        metric_fig = make_multi_metric_bar_chart(summary, metric="mape")
        anomaly_fig = make_multi_anomaly_chart(summary)

        self.assertEqual(len(metric_fig.data), 1)
        self.assertEqual(list(metric_fig.data[0].x), ["AAPL", "TSLA"])
        self.assertEqual(len(anomaly_fig.data), 1)
        self.assertEqual(list(anomaly_fig.data[0].x), ["TSLA", "AAPL"])

    def test_components_chart_renders_available_components(self) -> None:
        forecast = pd.DataFrame(
            {
                "ds": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "trend": [10.0, 10.5],
                "weekly": [0.1, -0.1],
                "yearly": [1.0, 1.1],
            }
        )

        fig = make_components_chart(forecast)

        self.assertEqual(len(fig.data), 3)
        self.assertEqual([trace.name for trace in fig.data], ["Trend", "Weekly", "Yearly"])


if __name__ == "__main__":
    unittest.main()
