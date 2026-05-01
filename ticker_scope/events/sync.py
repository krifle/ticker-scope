from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pandas as pd

from ticker_scope.data.database import get_connection, init_database
from ticker_scope.data.repositories import (
    add_event,
    get_recent_sync_runs,
    list_events,
    record_sync_run,
)
from ticker_scope.events.providers import (
    ALPHA_VANTAGE_EARNINGS_SOURCE,
    AlphaVantageEarningsClient,
    EarningsCalendarRequest,
)


@dataclass(frozen=True)
class EventSyncResult:
    fetched_rows: int
    inserted_rows: int
    skipped_duplicates: int
    from_cache: bool
    message: str


def sync_earnings_events(
    symbol: str,
    horizon: str = "3month",
    api_key: str | None = None,
    force_refresh: bool = False,
    min_refresh_hours: int = 12,
    client: AlphaVantageEarningsClient | None = None,
) -> EventSyncResult:
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("Ticker symbol is required.")

    init_database()
    started_at = _utc_now()
    source = ALPHA_VANTAGE_EARNINGS_SOURCE

    with get_connection() as connection:
        if not force_refresh and _recent_success_exists(
            connection,
            ticker=symbol,
            source=source,
            min_refresh_hours=min_refresh_hours,
        ):
            message = f"skipped API call; latest successful sync is within {min_refresh_hours}h"
            record_sync_run(
                connection,
                source=source,
                ticker=symbol,
                period=horizon,
                interval="event",
                status="skipped",
                row_count=0,
                started_at=started_at,
                message=message,
            )
            connection.commit()
            return EventSyncResult(
                fetched_rows=0,
                inserted_rows=0,
                skipped_duplicates=0,
                from_cache=True,
                message=message,
            )

        try:
            event_client = client or AlphaVantageEarningsClient()
            events = event_client.fetch_earnings_calendar(
                EarningsCalendarRequest(
                    symbol=symbol,
                    horizon=horizon,
                    api_key=api_key,
                )
            )
            inserted_rows, skipped_duplicates = merge_external_events(
                connection,
                events,
            )
            message = (
                f"synced {inserted_rows} events "
                f"({skipped_duplicates} duplicates skipped)"
            )
            record_sync_run(
                connection,
                source=source,
                ticker=symbol,
                period=horizon,
                interval="event",
                status="success",
                row_count=inserted_rows,
                started_at=started_at,
                message=message,
            )
            connection.commit()
            return EventSyncResult(
                fetched_rows=len(events),
                inserted_rows=inserted_rows,
                skipped_duplicates=skipped_duplicates,
                from_cache=False,
                message=message,
            )
        except Exception as exc:
            record_sync_run(
                connection,
                source=source,
                ticker=symbol,
                period=horizon,
                interval="event",
                status="failed",
                row_count=0,
                started_at=started_at,
                message=str(exc),
            )
            connection.commit()
            raise


def merge_external_events(
    connection,
    events: pd.DataFrame,
) -> tuple[int, int]:
    if events.empty:
        return 0, 0

    inserted_rows = 0
    skipped_duplicates = 0
    for row in events.to_dict("records"):
        ticker = str(row.get("ticker", "")).strip().upper()
        event_date = row.get("event_date")
        category = str(row.get("category", "earnings")).strip().lower() or "earnings"
        if not ticker or pd.isna(event_date):
            continue

        if _event_exists(
            connection,
            ticker=ticker,
            event_date=event_date,
            category=category,
        ):
            skipped_duplicates += 1
            continue

        add_event(
            connection,
            name=str(row.get("name") or f"{ticker} earnings"),
            event_date=event_date,
            category=category,
            ticker=ticker,
            lower_window=int(row.get("lower_window", -1) or 0),
            upper_window=int(row.get("upper_window", 1) or 0),
            source=str(row.get("source") or ALPHA_VANTAGE_EARNINGS_SOURCE),
            notes=row.get("notes"),
        )
        inserted_rows += 1

    return inserted_rows, skipped_duplicates


def _event_exists(
    connection,
    ticker: str,
    event_date,
    category: str,
) -> bool:
    existing_events = list_events(
        connection,
        ticker=ticker,
        include_global=False,
        start_date=event_date,
        end_date=event_date,
    )
    if existing_events.empty:
        return False

    normalized_date = pd.Timestamp(event_date).date()
    return not existing_events[
        (existing_events["ticker"] == ticker)
        & (existing_events["event_date"] == normalized_date)
        & (existing_events["category"].str.lower() == category)
    ].empty


def _recent_success_exists(
    connection,
    ticker: str,
    source: str,
    min_refresh_hours: int,
) -> bool:
    recent_runs = get_recent_sync_runs(connection, ticker=ticker, limit=20)
    if recent_runs.empty:
        return False

    threshold = datetime.now(UTC) - timedelta(hours=min_refresh_hours)
    for row in recent_runs.to_dict("records"):
        if row.get("source") != source or row.get("status") != "success":
            continue
        finished_at = pd.to_datetime(row.get("finished_at"), errors="coerce", utc=True)
        if pd.notna(finished_at) and finished_at.to_pydatetime() >= threshold:
            return True
    return False


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
