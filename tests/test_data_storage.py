from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from ticker_scope.date_policy import AUTO_BY_TICKER, KOREA_STOCK_MARKET
from ticker_scope.data.database import (
    CURRENT_SCHEMA_VERSION,
    get_connection,
    get_schema_version,
    init_database,
)
from ticker_scope.data.repositories import (
    add_event,
    delete_event,
    find_missing_price_ranges,
    get_daily_prices,
    get_fear_greed_history,
    get_price_coverage,
    list_events,
    list_backtest_metrics,
    list_backtest_runs,
    record_backtest_metrics,
    record_backtest_run,
    upsert_daily_prices,
    upsert_fear_greed_index,
)
from ticker_scope.events.calendar import events_to_holidays


class DataStorageTests(unittest.TestCase):
    def test_database_init_records_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"

            init_database(db_path)

            self.assertEqual(get_schema_version(db_path), CURRENT_SCHEMA_VERSION)
            with get_connection(db_path) as connection:
                rows = connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()

            self.assertEqual([row["version"] for row in rows], [1, 2, 3, 4, 5])

    def test_upsert_normalizes_duplicate_dates(self) -> None:
        history = pd.DataFrame(
            {
                "Date": ["2024-01-02", "2024-01-02", "2024-01-03"],
                "Open": [9.0, 10.0, 11.0],
                "High": [10.0, 11.0, 12.0],
                "Low": [8.0, 9.0, 10.0],
                "Close": [10.0, 11.0, 12.0],
                "Volume": [100, 200, 300],
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)

            with get_connection(db_path) as connection:
                stored_rows = upsert_daily_prices(connection, "TSLA", history)
                prices = get_daily_prices(connection, "TSLA")

            self.assertEqual(stored_rows, 2)
            self.assertEqual(len(prices), 2)
            self.assertEqual(float(prices.iloc[0]["Close"]), 11.0)

    def test_upsert_rejects_invalid_prices(self) -> None:
        history = pd.DataFrame(
            {
                "Date": ["2024-01-02"],
                "Close": [0.0],
                "Volume": [100],
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)

            with get_connection(db_path) as connection:
                with self.assertRaisesRegex(ValueError, "Close price must be positive"):
                    upsert_daily_prices(connection, "TSLA", history)

    def test_coverage_detects_long_missing_business_day_runs(self) -> None:
        history = pd.DataFrame(
            {
                "Date": ["2024-01-02", "2024-01-03", "2024-01-12"],
                "Close": [10.0, 11.0, 12.0],
                "Volume": [100, 200, 300],
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)

            with get_connection(db_path) as connection:
                upsert_daily_prices(connection, "TSLA", history)
                coverage = get_price_coverage(
                    connection,
                    "TSLA",
                    start_date=date(2024, 1, 2),
                    end_date=date(2024, 1, 12),
                    today=date(2024, 1, 13),
                )
                missing_ranges = find_missing_price_ranges(
                    connection,
                    "TSLA",
                    start_date=date(2024, 1, 2),
                    end_date=date(2024, 1, 12),
                    min_business_day_run=5,
                )

            self.assertEqual(coverage.row_count, 3)
            self.assertEqual(coverage.longest_missing_business_day_run, 6)
            self.assertEqual(
                missing_ranges,
                [(date(2024, 1, 4), date(2024, 1, 11), 6)],
            )

    def test_stock_coverage_ignores_nyse_holidays(self) -> None:
        history = pd.DataFrame(
            {
                "Date": ["2024-03-28", "2024-04-01"],
                "Close": [10.0, 11.0],
                "Volume": [100, 200],
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)

            with get_connection(db_path) as connection:
                upsert_daily_prices(connection, "TSLA", history)
                coverage = get_price_coverage(
                    connection,
                    "TSLA",
                    start_date=date(2024, 3, 28),
                    end_date=date(2024, 4, 1),
                    today=date(2024, 4, 2),
                )
                missing_ranges = find_missing_price_ranges(
                    connection,
                    "TSLA",
                    start_date=date(2024, 3, 28),
                    end_date=date(2024, 4, 1),
                    min_business_day_run=1,
                )

            self.assertEqual(coverage.missing_business_days, 0)
            self.assertEqual(coverage.longest_missing_business_day_run, 0)
            self.assertEqual(missing_ranges, [])

    def test_korea_stock_coverage_uses_korean_market_holidays(self) -> None:
        history = pd.DataFrame(
            {
                "Date": ["2025-04-30", "2025-05-02", "2025-05-07"],
                "Close": [10.0, 11.0, 12.0],
                "Volume": [100, 200, 300],
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)

            with get_connection(db_path) as connection:
                upsert_daily_prices(connection, "034020.KS", history)
                coverage = get_price_coverage(
                    connection,
                    "034020.KS",
                    start_date=date(2025, 4, 30),
                    end_date=date(2025, 5, 7),
                    today=date(2025, 5, 8),
                    date_policy=KOREA_STOCK_MARKET,
                )
                missing_ranges = find_missing_price_ranges(
                    connection,
                    "034020.KS",
                    start_date=date(2025, 4, 30),
                    end_date=date(2025, 5, 7),
                    min_business_day_run=1,
                    date_policy=AUTO_BY_TICKER,
                )

            self.assertEqual(coverage.missing_business_days, 0)
            self.assertEqual(coverage.longest_missing_business_day_run, 0)
            self.assertEqual(missing_ranges, [])

    def test_events_can_be_saved_listed_converted_and_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)

            with get_connection(db_path) as connection:
                global_id = add_event(
                    connection,
                    name="CPI",
                    event_date=date(2024, 1, 11),
                    category="macro",
                    ticker=None,
                    lower_window=-1,
                    upper_window=1,
                )
                tsla_id = add_event(
                    connection,
                    name="Earnings",
                    event_date=date(2024, 1, 24),
                    category="earnings",
                    ticker="TSLA",
                )
                connection.commit()

                events = list_events(connection, ticker="TSLA", include_global=True)
                holidays = events_to_holidays(events)
                deleted = delete_event(connection, global_id)
                remaining = list_events(connection, ticker="TSLA", include_global=True)

            self.assertEqual(len(events), 2)
            self.assertEqual(set(events["id"].astype(int)), {global_id, tsla_id})
            self.assertEqual(list(holidays.columns), ["holiday", "ds", "lower_window", "upper_window"])
            self.assertTrue(deleted)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(int(remaining.iloc[0]["id"]), tsla_id)

    def test_backtest_results_can_be_saved_and_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)

            metrics = pd.DataFrame(
                [
                    {
                        "horizon_days": 7,
                        "cutoff_date": "2024-03-01",
                        "train_start_date": "2024-01-02",
                        "train_end_date": "2024-03-01",
                        "test_start_date": "2024-03-04",
                        "test_end_date": "2024-03-08",
                        "test_rows": 5,
                        "mae": 1.2,
                        "rmse": 1.5,
                        "mape": 2.0,
                        "coverage": 80.0,
                    }
                ]
            )

            with get_connection(db_path) as connection:
                run_id = record_backtest_run(
                    connection,
                    ticker="TSLA",
                    strategy="rolling",
                    period="5y",
                    interval="1d",
                    adjusted=True,
                    interval_width=0.8,
                    use_events=True,
                    event_count=2,
                    row_count=100,
                    data_start_date="2024-01-02",
                    data_end_date="2024-03-29",
                    horizons_days=[7, 30],
                    rolling_windows=4,
                    min_train_rows=60,
                )
                saved_count = record_backtest_metrics(connection, run_id, metrics)
                connection.commit()

                runs = list_backtest_runs(connection, ticker="TSLA")
                saved_metrics = list_backtest_metrics(connection, ticker="TSLA")

            self.assertEqual(saved_count, 1)
            self.assertEqual(len(runs), 1)
            self.assertEqual(len(saved_metrics), 1)
            self.assertEqual(int(saved_metrics.iloc[0]["run_id"]), run_id)
            self.assertEqual(int(saved_metrics.iloc[0]["horizon_days"]), 7)
            self.assertEqual(saved_metrics.iloc[0]["date_policy"], "us_stock_market")
            self.assertTrue(bool(saved_metrics.iloc[0]["use_events"]))

    def test_fear_greed_history_prefers_manual_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ticker_scope.sqlite3"
            init_database(db_path)

            with get_connection(db_path) as connection:
                api_rows = pd.DataFrame(
                    {
                        "index_date": ["2024-01-02", "2024-01-03"],
                        "value": [30, 40],
                        "classification": ["Fear", "Fear"],
                    }
                )
                manual_rows = pd.DataFrame(
                    {
                        "index_date": ["2024-01-03"],
                        "value": [55],
                        "notes": ["manual correction"],
                    }
                )
                api_count = upsert_fear_greed_index(
                    connection,
                    api_rows,
                    source="cnn_api",
                )
                manual_count = upsert_fear_greed_index(
                    connection,
                    manual_rows,
                    source="manual",
                )
                history = get_fear_greed_history(connection)

            self.assertEqual(api_count, 2)
            self.assertEqual(manual_count, 1)
            self.assertEqual(len(history), 2)
            self.assertEqual(history.iloc[1]["index_date"], date(2024, 1, 3))
            self.assertEqual(float(history.iloc[1]["value"]), 55.0)
            self.assertEqual(history.iloc[1]["source"], "manual")


if __name__ == "__main__":
    unittest.main()
