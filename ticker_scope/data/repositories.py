from __future__ import annotations

from dataclasses import dataclass
import json
import math
import sqlite3
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from ticker_scope.date_policy import (
    US_STOCK_MARKET,
    expected_dates_between,
    normalize_date_policy,
    next_expected_date,
    resolve_date_policy_for_symbol,
)


@dataclass(frozen=True)
class PriceCoverage:
    ticker: str
    interval: str
    adjusted: bool
    start_date: date | None
    end_date: date | None
    row_count: int
    missing_business_days: int
    longest_missing_business_day_run: int
    freshness_days: int | None


EVENT_CATEGORIES = (
    "earnings",
    "macro",
    "split",
    "dividend",
    "product",
    "manual",
    "service",
)

FEAR_GREED_SOURCE_PRIORITY = {
    "manual": 0,
    "csv_import": 1,
    "cnn_api": 2,
}


def upsert_symbol(
    connection: sqlite3.Connection,
    ticker: str,
    name: str | None = None,
    exchange: str | None = None,
    currency: str | None = None,
) -> None:
    now = _utc_now()
    connection.execute(
        """
        INSERT INTO symbols (
          ticker, name, exchange, currency, is_active, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
          name = COALESCE(excluded.name, symbols.name),
          exchange = COALESCE(excluded.exchange, symbols.exchange),
          currency = COALESCE(excluded.currency, symbols.currency),
          is_active = 1,
          updated_at = excluded.updated_at
        """,
        (ticker.upper(), name, exchange, currency, now, now),
    )


def add_event(
    connection: sqlite3.Connection,
    name: str,
    event_date: date | str,
    category: str = "manual",
    ticker: str | None = None,
    lower_window: int = 0,
    upper_window: int = 0,
    source: str = "manual",
    notes: str | None = None,
) -> int:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Event name is required.")

    normalized_ticker = _normalize_optional_ticker(ticker)
    if normalized_ticker is not None:
        upsert_symbol(connection, normalized_ticker)

    normalized_category = category.strip().lower() or "manual"
    normalized_source = source.strip().lower() or "manual"
    now = _utc_now()

    cursor = connection.execute(
        """
        INSERT INTO events (
          name, event_date, category, ticker, lower_window, upper_window,
          source, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_name,
            _date_string(event_date),
            normalized_category,
            normalized_ticker,
            int(lower_window),
            int(upper_window),
            normalized_source,
            _normalize_optional_text(notes),
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def list_events(
    connection: sqlite3.Connection,
    ticker: str | None = None,
    include_global: bool = True,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> pd.DataFrame:
    query = """
        SELECT
          id,
          name,
          event_date,
          category,
          ticker,
          lower_window,
          upper_window,
          source,
          notes,
          created_at,
          updated_at
        FROM events
        WHERE 1 = 1
    """
    params: list[Any] = []

    normalized_ticker = _normalize_optional_ticker(ticker)
    if normalized_ticker is not None:
        if include_global:
            query += " AND (ticker = ? OR ticker IS NULL)"
            params.append(normalized_ticker)
        else:
            query += " AND ticker = ?"
            params.append(normalized_ticker)
    elif not include_global:
        query += " AND ticker IS NOT NULL"

    if start_date is not None:
        query += " AND event_date >= ?"
        params.append(_date_string(start_date))
    if end_date is not None:
        query += " AND event_date <= ?"
        params.append(_date_string(end_date))

    query += " ORDER BY event_date DESC, id DESC"
    result = pd.read_sql_query(query, connection, params=params)
    if result.empty:
        return result

    result["event_date"] = pd.to_datetime(result["event_date"]).dt.date
    for column in ("lower_window", "upper_window"):
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(int)
    return result


def delete_event(connection: sqlite3.Connection, event_id: int) -> bool:
    cursor = connection.execute("DELETE FROM events WHERE id = ?", (int(event_id),))
    return cursor.rowcount > 0


def upsert_daily_prices(
    connection: sqlite3.Connection,
    ticker: str,
    history: pd.DataFrame,
    interval: str = "1d",
    adjusted: bool = True,
    source: str = "yfinance",
) -> int:
    normalized = normalize_daily_price_history(history)
    if normalized.empty:
        return 0

    upsert_symbol(connection, ticker)

    now = _utc_now()
    rows = []

    for row in normalized.itertuples(index=False):
        row_dict = row._asdict()
        rows.append(
            (
                ticker.upper(),
                row_dict["Date"].isoformat(),
                interval,
                _optional_float(row_dict.get("Open")),
                _optional_float(row_dict.get("High")),
                _optional_float(row_dict.get("Low")),
                _required_float(row_dict.get("Close")),
                _optional_int(row_dict.get("Volume")),
                int(adjusted),
                source,
                now,
                now,
            )
        )

    if not rows:
        return 0

    connection.executemany(
        """
        INSERT INTO daily_prices (
          ticker, price_date, interval, open, high, low, close, volume,
          adjusted, source, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, price_date, interval, adjusted) DO UPDATE SET
          open = excluded.open,
          high = excluded.high,
          low = excluded.low,
          close = excluded.close,
          volume = excluded.volume,
          source = excluded.source,
          updated_at = excluded.updated_at
        """,
        rows,
    )
    return len(rows)


def normalize_daily_price_history(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return history.copy()

    required_columns = {"Date", "Close"}
    missing_columns = required_columns - set(history.columns)
    if missing_columns:
        raise ValueError(f"Missing required price columns: {sorted(missing_columns)}")

    normalized = history.copy()
    normalized["Date"] = pd.to_datetime(
        normalized["Date"],
        errors="coerce",
    ).dt.date

    numeric_columns = ["Open", "High", "Low", "Close", "Volume"]
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.dropna(subset=["Date", "Close"])
    if normalized.empty:
        raise ValueError("No valid price rows after normalization.")

    invalid_close = normalized["Close"] <= 0
    if invalid_close.any():
        invalid_dates = normalized.loc[invalid_close, "Date"].astype(str).tolist()
        raise ValueError(
            "Close price must be positive. "
            f"Invalid dates: {', '.join(invalid_dates[:5])}"
        )

    if "Volume" in normalized.columns:
        invalid_volume = normalized["Volume"].notna() & (normalized["Volume"] < 0)
        if invalid_volume.any():
            invalid_dates = normalized.loc[invalid_volume, "Date"].astype(str).tolist()
            raise ValueError(
                "Volume must be zero or positive. "
                f"Invalid dates: {', '.join(invalid_dates[:5])}"
            )

    normalized = normalized.drop_duplicates(subset=["Date"], keep="last")
    return normalized.sort_values("Date").reset_index(drop=True)


def get_daily_prices(
    connection: sqlite3.Connection,
    ticker: str,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    interval: str = "1d",
    adjusted: bool = True,
) -> pd.DataFrame:
    query = """
        SELECT
          price_date AS Date,
          open AS Open,
          high AS High,
          low AS Low,
          close AS Close,
          volume AS Volume,
          ticker AS Symbol
        FROM daily_prices
        WHERE ticker = ?
          AND interval = ?
          AND adjusted = ?
    """
    params: list[Any] = [ticker.upper(), interval, int(adjusted)]

    if start_date is not None:
        query += " AND price_date >= ?"
        params.append(_date_string(start_date))
    if end_date is not None:
        query += " AND price_date <= ?"
        params.append(_date_string(end_date))

    query += " ORDER BY price_date"

    result = pd.read_sql_query(query, connection, params=params)
    if result.empty:
        return result

    result["Date"] = pd.to_datetime(result["Date"])
    for column in ("Open", "High", "Low", "Close", "Volume"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def get_price_dates(
    connection: sqlite3.Connection,
    ticker: str,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    interval: str = "1d",
    adjusted: bool = True,
) -> list[date]:
    query = """
        SELECT price_date
        FROM daily_prices
        WHERE ticker = ?
          AND interval = ?
          AND adjusted = ?
    """
    params: list[Any] = [ticker.upper(), interval, int(adjusted)]

    if start_date is not None:
        query += " AND price_date >= ?"
        params.append(_date_string(start_date))
    if end_date is not None:
        query += " AND price_date <= ?"
        params.append(_date_string(end_date))

    query += " ORDER BY price_date"
    rows = connection.execute(query, params).fetchall()
    return [date.fromisoformat(row["price_date"]) for row in rows]


def get_price_coverage(
    connection: sqlite3.Connection,
    ticker: str,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    interval: str = "1d",
    adjusted: bool = True,
    today: date | None = None,
    date_policy: str = US_STOCK_MARKET,
) -> PriceCoverage:
    effective_date_policy = resolve_date_policy_for_symbol(ticker, date_policy)
    query = """
        SELECT
          COUNT(*) AS row_count,
          MIN(price_date) AS start_date,
          MAX(price_date) AS end_date
        FROM daily_prices
        WHERE ticker = ?
          AND interval = ?
          AND adjusted = ?
    """
    params: list[Any] = [ticker.upper(), interval, int(adjusted)]

    if start_date is not None:
        query += " AND price_date >= ?"
        params.append(_date_string(start_date))
    if end_date is not None:
        query += " AND price_date <= ?"
        params.append(_date_string(end_date))

    row = connection.execute(query, params).fetchone()
    row_count = int(row["row_count"])
    stored_start = (
        date.fromisoformat(row["start_date"]) if row["start_date"] is not None else None
    )
    stored_end = (
        date.fromisoformat(row["end_date"]) if row["end_date"] is not None else None
    )

    missing_runs = []
    if stored_start is not None and stored_end is not None:
        coverage_start = _max_date(stored_start, _optional_date(start_date))
        coverage_end = _min_date(stored_end, _optional_date(end_date))
        dates = get_price_dates(
            connection,
            ticker=ticker,
            start_date=coverage_start,
            end_date=coverage_end,
            interval=interval,
            adjusted=adjusted,
        )
        missing_runs = _missing_business_day_runs(
            dates,
            coverage_start,
            coverage_end,
            date_policy=effective_date_policy,
        )

    freshness_days = None
    if stored_end is not None:
        freshness_days = ((today or date.today()) - stored_end).days

    return PriceCoverage(
        ticker=ticker.upper(),
        interval=interval,
        adjusted=adjusted,
        start_date=stored_start,
        end_date=stored_end,
        row_count=row_count,
        missing_business_days=sum(len(run) for run in missing_runs),
        longest_missing_business_day_run=max((len(run) for run in missing_runs), default=0),
        freshness_days=freshness_days,
    )


def find_missing_price_ranges(
    connection: sqlite3.Connection,
    ticker: str,
    start_date: date,
    end_date: date,
    interval: str = "1d",
    adjusted: bool = True,
    min_business_day_run: int = 5,
    date_policy: str = US_STOCK_MARKET,
) -> list[tuple[date, date, int]]:
    effective_date_policy = resolve_date_policy_for_symbol(ticker, date_policy)
    dates = get_price_dates(
        connection,
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        adjusted=adjusted,
    )
    missing_runs = _missing_business_day_runs(
        dates,
        start_date,
        end_date,
        date_policy=effective_date_policy,
    )
    return [
        (run[0], run[-1], len(run))
        for run in missing_runs
        if len(run) >= min_business_day_run
    ]


def get_first_price_date(
    connection: sqlite3.Connection,
    ticker: str,
    interval: str = "1d",
    adjusted: bool = True,
) -> date | None:
    return _single_date(
        connection,
        """
        SELECT MIN(price_date) AS value
        FROM daily_prices
        WHERE ticker = ? AND interval = ? AND adjusted = ?
        """,
        (ticker.upper(), interval, int(adjusted)),
    )


def get_last_price_date(
    connection: sqlite3.Connection,
    ticker: str,
    interval: str = "1d",
    adjusted: bool = True,
) -> date | None:
    return _single_date(
        connection,
        """
        SELECT MAX(price_date) AS value
        FROM daily_prices
        WHERE ticker = ? AND interval = ? AND adjusted = ?
        """,
        (ticker.upper(), interval, int(adjusted)),
    )


def get_database_summary(connection: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "symbols",
        "daily_prices",
        "events",
        "sync_runs",
        "backtest_runs",
        "backtest_metrics",
        "fear_greed_index",
        "schema_migrations",
    )
    summary = {}
    for table in tables:
        row = connection.execute(f"SELECT COUNT(*) AS value FROM {table}").fetchone()
        summary[table] = int(row["value"])
    return summary


def classify_fear_greed_value(value: float) -> str:
    score = float(value)
    if score < 0 or score > 100:
        raise ValueError("Fear & Greed value must be between 0 and 100.")
    if score <= 24:
        return "Extreme Fear"
    if score <= 44:
        return "Fear"
    if score <= 55:
        return "Neutral"
    if score <= 75:
        return "Greed"
    return "Extreme Greed"


def upsert_fear_greed_index(
    connection: sqlite3.Connection,
    data: pd.DataFrame,
    source: str = "manual",
) -> int:
    normalized = normalize_fear_greed_history(data, source=source)
    if normalized.empty:
        return 0

    now = _utc_now()
    rows = []
    for row in normalized.to_dict("records"):
        rows.append(
            (
                row["source"],
                row["index_date"].isoformat(),
                float(row["value"]),
                _normalize_optional_text(row.get("classification"))
                or classify_fear_greed_value(float(row["value"])),
                _optional_int(row.get("raw_timestamp")),
                _normalize_optional_text(row.get("notes")),
                now,
                now,
            )
        )

    connection.executemany(
        """
        INSERT INTO fear_greed_index (
          source, index_date, value, classification, raw_timestamp, notes,
          created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, index_date) DO UPDATE SET
          value = excluded.value,
          classification = excluded.classification,
          raw_timestamp = excluded.raw_timestamp,
          notes = excluded.notes,
          updated_at = excluded.updated_at
        """,
        rows,
    )
    return len(rows)


def normalize_fear_greed_history(
    data: pd.DataFrame,
    source: str = "manual",
) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame(
            columns=[
                "source",
                "index_date",
                "value",
                "classification",
                "raw_timestamp",
                "notes",
            ]
        )

    normalized_source = _normalize_source(source)
    normalized = data.copy()
    if "index_date" not in normalized.columns and "date" in normalized.columns:
        normalized = normalized.rename(columns={"date": "index_date"})
    if "score" in normalized.columns and "value" not in normalized.columns:
        normalized = normalized.rename(columns={"score": "value"})
    if "rating" in normalized.columns and "classification" not in normalized.columns:
        normalized = normalized.rename(columns={"rating": "classification"})

    required_columns = {"index_date", "value"}
    missing_columns = required_columns - set(normalized.columns)
    if missing_columns:
        raise ValueError(
            f"Missing required Fear & Greed columns: {sorted(missing_columns)}"
        )

    normalized["source"] = normalized.get("source", normalized_source)
    normalized["source"] = normalized["source"].fillna(normalized_source).map(_normalize_source)
    normalized["index_date"] = pd.to_datetime(
        normalized["index_date"],
        errors="coerce",
    ).dt.date
    normalized["value"] = pd.to_numeric(normalized["value"], errors="coerce")
    if "classification" not in normalized.columns:
        normalized["classification"] = None
    if "raw_timestamp" not in normalized.columns:
        normalized["raw_timestamp"] = None
    if "notes" not in normalized.columns:
        normalized["notes"] = None

    normalized = normalized.dropna(subset=["index_date", "value"])
    normalized = normalized[
        normalized["value"].between(0, 100, inclusive="both")
    ].copy()
    if normalized.empty:
        return normalized

    missing_classification = normalized["classification"].isna() | (
        normalized["classification"].astype(str).str.strip() == ""
    )
    normalized.loc[missing_classification, "classification"] = normalized.loc[
        missing_classification,
        "value",
    ].map(classify_fear_greed_value)

    selected_columns = [
        "source",
        "index_date",
        "value",
        "classification",
        "raw_timestamp",
        "notes",
    ]
    normalized = normalized[selected_columns]
    return normalized.drop_duplicates(
        subset=["source", "index_date"],
        keep="last",
    ).sort_values("index_date")


def get_fear_greed_history(
    connection: sqlite3.Connection,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    preferred_sources: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    query = """
        SELECT
          id,
          source,
          index_date,
          value,
          classification,
          raw_timestamp,
          notes,
          created_at,
          updated_at
        FROM fear_greed_index
        WHERE 1 = 1
    """
    params: list[Any] = []
    if start_date is not None:
        query += " AND index_date >= ?"
        params.append(_date_string(start_date))
    if end_date is not None:
        query += " AND index_date <= ?"
        params.append(_date_string(end_date))
    if preferred_sources:
        normalized_sources = [_normalize_source(source) for source in preferred_sources]
        placeholders = ", ".join("?" for _ in normalized_sources)
        query += f" AND source IN ({placeholders})"
        params.extend(normalized_sources)

    result = pd.read_sql_query(query, connection, params=params)
    if result.empty:
        return result

    result["index_date"] = pd.to_datetime(result["index_date"]).dt.date
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result["_source_rank"] = result["source"].map(_fear_greed_source_rank)
    result = (
        result.sort_values(["index_date", "_source_rank", "id"])
        .drop_duplicates(subset=["index_date"], keep="first")
        .drop(columns=["_source_rank"])
        .sort_values("index_date")
        .reset_index(drop=True)
    )
    return result


def list_fear_greed_values(
    connection: sqlite3.Connection,
    limit: int = 500,
) -> pd.DataFrame:
    result = pd.read_sql_query(
        """
        SELECT
          id,
          source,
          index_date,
          value,
          classification,
          raw_timestamp,
          notes,
          created_at,
          updated_at
        FROM fear_greed_index
        ORDER BY index_date DESC, id DESC
        LIMIT ?
        """,
        connection,
        params=[int(limit)],
    )
    if result.empty:
        return result
    result["index_date"] = pd.to_datetime(result["index_date"]).dt.date
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    return result


def delete_fear_greed_value(connection: sqlite3.Connection, value_id: int) -> bool:
    cursor = connection.execute(
        "DELETE FROM fear_greed_index WHERE id = ?",
        (int(value_id),),
    )
    return cursor.rowcount > 0


def get_fear_greed_coverage(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
          COUNT(*) AS row_count,
          MIN(index_date) AS start_date,
          MAX(index_date) AS end_date
        FROM fear_greed_index
        """
    ).fetchone()
    latest_history = get_fear_greed_history(
        connection,
        start_date=row["end_date"],
        end_date=row["end_date"],
    )
    latest = latest_history.iloc[0].to_dict() if not latest_history.empty else None
    return {
        "row_count": int(row["row_count"]),
        "start_date": (
            date.fromisoformat(row["start_date"])
            if row["start_date"] is not None
            else None
        ),
        "end_date": (
            date.fromisoformat(row["end_date"])
            if row["end_date"] is not None
            else None
        ),
        "latest_date": (
            latest["index_date"] if latest is not None else None
        ),
        "latest_value": (
            float(latest["value"])
            if latest is not None and latest["value"] is not None
            else None
        ),
        "latest_classification": latest["classification"] if latest is not None else None,
        "latest_source": latest["source"] if latest is not None else None,
    }


def get_recent_sync_runs(
    connection: sqlite3.Connection,
    ticker: str | None = None,
    limit: int = 20,
) -> pd.DataFrame:
    query = """
        SELECT
          id,
          source,
          ticker,
          period,
          interval,
          status,
          row_count,
          message,
          started_at,
          finished_at
        FROM sync_runs
    """
    params: list[Any] = []
    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker.upper())
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return pd.read_sql_query(query, connection, params=params)


def record_sync_run(
    connection: sqlite3.Connection,
    source: str,
    ticker: str,
    period: str | None,
    interval: str,
    status: str,
    row_count: int,
    started_at: str,
    message: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO sync_runs (
          source, ticker, period, interval, status, row_count, message,
          started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            ticker.upper(),
            period,
            interval,
            status,
            row_count,
            message,
            started_at,
            _utc_now(),
        ),
    )


def record_backtest_run(
    connection: sqlite3.Connection,
    ticker: str,
    strategy: str,
    period: str | None,
    interval: str,
    adjusted: bool,
    interval_width: float,
    use_events: bool,
    event_count: int,
    row_count: int,
    data_start_date: date | str | None,
    data_end_date: date | str | None,
    date_policy: str = US_STOCK_MARKET,
    status: str = "success",
    train_ratio: float | None = None,
    horizons_days: list[int] | tuple[int, ...] | None = None,
    rolling_windows: int | None = None,
    min_train_rows: int | None = None,
    message: str | None = None,
) -> int:
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        raise ValueError("Ticker is required.")
    effective_date_policy = resolve_date_policy_for_symbol(
        normalized_ticker,
        date_policy,
    )

    upsert_symbol(connection, normalized_ticker)
    cursor = connection.execute(
        """
        INSERT INTO backtest_runs (
          ticker, strategy, period, interval, adjusted, train_ratio, horizons,
          rolling_windows, min_train_rows, interval_width, use_events, event_count,
          date_policy, row_count, data_start_date, data_end_date, status, message,
          created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_ticker,
            strategy.strip().lower(),
            period,
            interval,
            int(adjusted),
            train_ratio,
            _json_horizons(horizons_days),
            rolling_windows,
            min_train_rows,
            float(interval_width),
            int(use_events),
            int(event_count),
            effective_date_policy,
            int(row_count),
            _optional_date_string(data_start_date),
            _optional_date_string(data_end_date),
            status,
            _normalize_optional_text(message),
            _utc_now(),
        ),
    )
    return int(cursor.lastrowid)


def record_backtest_metrics(
    connection: sqlite3.Connection,
    run_id: int,
    metrics: pd.DataFrame,
) -> int:
    if metrics.empty:
        return 0

    now = _utc_now()
    rows = []
    for row in metrics.to_dict("records"):
        rows.append(
            (
                int(run_id),
                _optional_int(row.get("horizon_days")),
                _optional_date_string(row.get("cutoff_date")),
                _optional_date_string(row.get("train_start_date")),
                _optional_date_string(row.get("train_end_date")),
                _optional_date_string(row.get("test_start_date")),
                _optional_date_string(row.get("test_end_date")),
                int(row.get("test_rows", 0) or 0),
                _optional_float(row.get("mae")),
                _optional_float(row.get("rmse")),
                _optional_float(row.get("mape")),
                _optional_float(row.get("coverage")),
                now,
            )
        )

    connection.executemany(
        """
        INSERT INTO backtest_metrics (
          run_id, horizon_days, cutoff_date, train_start_date, train_end_date,
          test_start_date, test_end_date, test_rows, mae, rmse, mape, coverage,
          created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def list_backtest_runs(
    connection: sqlite3.Connection,
    ticker: str | None = None,
    limit: int = 50,
) -> pd.DataFrame:
    query = """
        SELECT
          id,
          ticker,
          strategy,
          period,
          interval,
          adjusted,
          train_ratio,
          horizons,
          rolling_windows,
          min_train_rows,
          interval_width,
          use_events,
          event_count,
          date_policy,
          row_count,
          data_start_date,
          data_end_date,
          status,
          message,
          created_at
        FROM backtest_runs
    """
    params: list[Any] = []
    normalized_ticker = _normalize_optional_ticker(ticker)
    if normalized_ticker is not None:
        query += " WHERE ticker = ?"
        params.append(normalized_ticker)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    return pd.read_sql_query(query, connection, params=params)


def list_backtest_metrics(
    connection: sqlite3.Connection,
    ticker: str | None = None,
    limit: int = 500,
) -> pd.DataFrame:
    query = """
        SELECT
          metrics.id AS metric_id,
          runs.id AS run_id,
          runs.ticker,
          runs.strategy,
          runs.period,
          runs.interval,
          runs.adjusted,
          runs.train_ratio,
          runs.horizons,
          runs.rolling_windows,
          runs.min_train_rows,
          runs.interval_width,
          runs.use_events,
          runs.event_count,
          runs.date_policy,
          runs.row_count,
          runs.data_start_date,
          runs.data_end_date,
          runs.status,
          runs.message,
          runs.created_at AS run_created_at,
          metrics.horizon_days,
          metrics.cutoff_date,
          metrics.train_start_date,
          metrics.train_end_date,
          metrics.test_start_date,
          metrics.test_end_date,
          metrics.test_rows,
          metrics.mae,
          metrics.rmse,
          metrics.mape,
          metrics.coverage,
          metrics.created_at AS metric_created_at
        FROM backtest_metrics AS metrics
        JOIN backtest_runs AS runs
          ON runs.id = metrics.run_id
    """
    params: list[Any] = []
    normalized_ticker = _normalize_optional_ticker(ticker)
    if normalized_ticker is not None:
        query += " WHERE runs.ticker = ?"
        params.append(normalized_ticker)
    query += " ORDER BY metrics.id DESC LIMIT ?"
    params.append(int(limit))
    result = pd.read_sql_query(query, connection, params=params)
    if result.empty:
        return result

    for column in ("adjusted", "use_events"):
        result[column] = result[column].astype(bool)
    for column in (
        "horizon_days",
        "rolling_windows",
        "min_train_rows",
        "event_count",
        "row_count",
        "test_rows",
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    for column in ("interval_width", "train_ratio", "mae", "rmse", "mape", "coverage"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def _single_date(
    connection: sqlite3.Connection,
    query: str,
    params: tuple[Any, ...],
) -> date | None:
    row = connection.execute(query, params).fetchone()
    if row is None or row["value"] is None:
        return None
    return date.fromisoformat(row["value"])


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _date_string(value: date | str) -> str:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)[:10]).isoformat()


def _optional_date_string(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return _date_string(value)


def _normalize_optional_ticker(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _normalize_source(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        raise ValueError("Source is required.")
    return normalized


def _fear_greed_source_rank(value: Any) -> int:
    return FEAR_GREED_SOURCE_PRIORITY.get(str(value or "").strip().lower(), 99)


def _normalize_optional_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _max_date(left: date, right: date | None) -> date:
    if right is None:
        return left
    return max(left, right)


def _min_date(left: date, right: date | None) -> date:
    if right is None:
        return left
    return min(left, right)


def _missing_business_day_runs(
    stored_dates: list[date],
    start_date: date,
    end_date: date,
    date_policy: str = US_STOCK_MARKET,
) -> list[list[date]]:
    if start_date > end_date:
        return []

    expected_dates = set(
        expected_dates_between(start_date, end_date, date_policy=date_policy)
    )
    missing_dates = sorted(expected_dates - set(stored_dates))
    if not missing_dates:
        return []

    runs: list[list[date]] = []
    current_run = [missing_dates[0]]
    for missing_date in missing_dates[1:]:
        expected_next = next_expected_date(
            current_run[-1],
            date_policy=date_policy,
        )
        if missing_date == expected_next:
            current_run.append(missing_date)
        else:
            runs.append(current_run)
            current_run = [missing_date]
    runs.append(current_run)
    return runs


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _required_float(value: Any) -> float:
    result = _optional_float(value)
    if result is None:
        raise ValueError("Close price is required.")
    return result


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return int(value)


def _json_horizons(horizons_days: list[int] | tuple[int, ...] | None) -> str | None:
    if horizons_days is None:
        return None
    return json.dumps([int(horizon) for horizon in horizons_days])
