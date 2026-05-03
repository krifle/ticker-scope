from __future__ import annotations

from datetime import date

import pandas as pd

from ticker_scope.data.database import get_connection, init_database
from ticker_scope.data.repositories import (
    add_event,
    delete_event,
    get_database_summary,
    get_price_coverage,
    get_recent_sync_runs,
    list_backtest_metrics,
    list_events,
    record_backtest_metrics,
    record_backtest_run,
)
from ticker_scope.data.sync import period_to_start_date


def load_storage_status(symbol: str, period: str, date_policy: str):
    init_database()
    with get_connection() as connection:
        return {
            "summary": get_database_summary(connection),
            "coverage": get_price_coverage(
                connection,
                ticker=symbol,
                start_date=period_to_start_date(period),
                end_date=date.today(),
                interval="1d",
                adjusted=True,
                date_policy=date_policy,
            ),
            "recent_sync_runs": get_recent_sync_runs(connection, ticker=symbol, limit=20),
        }


def load_model_events(symbol: str) -> pd.DataFrame:
    init_database()
    with get_connection() as connection:
        return list_events(connection, ticker=symbol, include_global=True)


def load_saved_backtest_metrics(symbol: str | None) -> pd.DataFrame:
    init_database()
    with get_connection() as connection:
        return list_backtest_metrics(connection, ticker=symbol, limit=1000)


def load_latest_sync_run(symbol: str) -> pd.Series | None:
    init_database()
    with get_connection() as connection:
        recent_runs = get_recent_sync_runs(connection, ticker=symbol, limit=1)
    if recent_runs.empty:
        return None
    return recent_runs.iloc[0]


def save_backtest_result(
    symbol: str,
    period: str,
    strategy: str,
    prophet_df: pd.DataFrame,
    metrics: pd.DataFrame,
    interval_width: float,
    use_events: bool,
    event_count: int,
    date_policy: str,
    train_ratio: float | None = None,
    horizons_days: list[int] | None = None,
    rolling_windows: int | None = None,
    min_train_rows: int | None = None,
) -> int:
    init_database()
    with get_connection() as connection:
        run_id = record_backtest_run(
            connection,
            ticker=symbol,
            strategy=strategy,
            period=period,
            interval="1d",
            adjusted=True,
            train_ratio=train_ratio,
            horizons_days=horizons_days,
            rolling_windows=rolling_windows,
            min_train_rows=min_train_rows,
            interval_width=interval_width,
            use_events=use_events,
            event_count=event_count,
            date_policy=date_policy,
            row_count=len(prophet_df),
            data_start_date=prophet_df.iloc[0]["ds"],
            data_end_date=prophet_df.iloc[-1]["ds"],
        )
        record_backtest_metrics(connection, run_id, metrics)
        connection.commit()
    return run_id


def save_manual_event(
    name: str,
    event_date: date,
    category: str,
    ticker: str,
    lower_window: int,
    upper_window: int,
    notes: str,
) -> None:
    init_database()
    with get_connection() as connection:
        add_event(
            connection,
            name=name,
            event_date=event_date,
            category=category,
            ticker=ticker,
            lower_window=lower_window,
            upper_window=upper_window,
            notes=notes,
        )
        connection.commit()


def remove_event(event_id: int) -> None:
    init_database()
    with get_connection() as connection:
        delete_event(connection, event_id)
        connection.commit()
