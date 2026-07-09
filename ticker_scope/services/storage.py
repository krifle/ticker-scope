from __future__ import annotations

from datetime import date

import pandas as pd

from ticker_scope.date_policy import resolve_date_policy_for_symbol
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
from ticker_scope.observability import get_logger


LOGGER = get_logger(__name__)


def load_storage_status(symbol: str, period: str, date_policy: str):
    effective_date_policy = resolve_date_policy_for_symbol(symbol, date_policy)
    init_database()
    with get_connection() as connection:
        summary = get_database_summary(connection)
        coverage = get_price_coverage(
            connection,
            ticker=symbol,
            start_date=period_to_start_date(period),
            end_date=date.today(),
            interval="1d",
            adjusted=True,
            date_policy=effective_date_policy,
        )
        recent_sync_runs = get_recent_sync_runs(connection, ticker=symbol, limit=20)
    LOGGER.info(
        "DB read storage_status ticker=%s price_rows=%s recent_sync_runs=%s",
        symbol.strip().upper(),
        coverage.row_count,
        len(recent_sync_runs),
    )
    return {
        "summary": summary,
        "coverage": coverage,
        "recent_sync_runs": recent_sync_runs,
    }


def load_model_events(symbol: str) -> pd.DataFrame:
    init_database()
    with get_connection() as connection:
        events = list_events(connection, ticker=symbol, include_global=True)
    LOGGER.info(
        "DB read table=events ticker=%s rows=%s include_global=True",
        symbol.strip().upper(),
        len(events),
    )
    return events


def load_saved_backtest_metrics(symbol: str | None) -> pd.DataFrame:
    init_database()
    with get_connection() as connection:
        metrics = list_backtest_metrics(connection, ticker=symbol, limit=1000)
    LOGGER.info(
        "DB read table=backtest_metrics ticker=%s rows=%s",
        symbol.strip().upper() if symbol else None,
        len(metrics),
    )
    return metrics


def load_latest_sync_run(symbol: str) -> pd.Series | None:
    init_database()
    with get_connection() as connection:
        recent_runs = get_recent_sync_runs(connection, ticker=symbol, limit=1)
    LOGGER.info(
        "DB read table=sync_runs ticker=%s rows=%s limit=1",
        symbol.strip().upper(),
        len(recent_runs),
    )
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
    LOGGER.info(
        "DB write tables=backtest_runs,backtest_metrics ticker=%s run_id=%s "
        "metric_rows=%s",
        symbol.strip().upper(),
        run_id,
        len(metrics),
    )
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
        event_id = add_event(
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
    LOGGER.info(
        "DB write table=events ticker=%s event_id=%s category=%s event_date=%s",
        ticker.strip().upper(),
        event_id,
        category,
        event_date,
    )


def remove_event(event_id: int) -> None:
    init_database()
    with get_connection() as connection:
        deleted = delete_event(connection, event_id)
        connection.commit()
    LOGGER.info("DB write table=events delete event_id=%s deleted=%s", event_id, deleted)
