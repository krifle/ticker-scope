from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ticker_scope.data.database import get_connection, init_database
from ticker_scope.data.repositories import (
    get_recent_sync_runs,
    record_sync_run,
    upsert_fear_greed_index,
)
from ticker_scope.sentiment.providers import (
    CNN_FEAR_GREED_SOURCE,
    CnnFearGreedClient,
    FearGreedClient,
)


CNN_FEAR_GREED_SYNC_SOURCE = "cnn_fear_greed"
SENTIMENT_SYNC_TICKER = "MARKET"


@dataclass(frozen=True)
class SentimentSyncResult:
    fetched_rows: int
    stored_rows: int
    from_cache: bool
    message: str


def sync_fear_greed_index(
    force_refresh: bool = False,
    min_refresh_hours: int = 12,
    client: FearGreedClient | None = None,
) -> SentimentSyncResult:
    init_database()
    started_at = _utc_now()

    with get_connection() as connection:
        if not force_refresh and _recent_success_exists(
            connection,
            min_refresh_hours=min_refresh_hours,
        ):
            message = (
                "skipped API call; latest successful sync "
                f"is within {min_refresh_hours}h"
            )
            record_sync_run(
                connection,
                source=CNN_FEAR_GREED_SYNC_SOURCE,
                ticker=SENTIMENT_SYNC_TICKER,
                period="1y",
                interval="sentiment",
                status="skipped",
                row_count=0,
                started_at=started_at,
                message=message,
            )
            connection.commit()
            return SentimentSyncResult(
                fetched_rows=0,
                stored_rows=0,
                from_cache=True,
                message=message,
            )

        try:
            sentiment_client = client or CnnFearGreedClient()
            history = sentiment_client.fetch_history(last="365")
            stored_rows = upsert_fear_greed_index(
                connection,
                history,
                source=CNN_FEAR_GREED_SOURCE,
            )
            message = f"synced {stored_rows} Fear & Greed rows"
            record_sync_run(
                connection,
                source=CNN_FEAR_GREED_SYNC_SOURCE,
                ticker=SENTIMENT_SYNC_TICKER,
                period="1y",
                interval="sentiment",
                status="success",
                row_count=stored_rows,
                started_at=started_at,
                message=message,
            )
            connection.commit()
            return SentimentSyncResult(
                fetched_rows=len(history),
                stored_rows=stored_rows,
                from_cache=False,
                message=message,
            )
        except Exception as exc:
            record_sync_run(
                connection,
                source=CNN_FEAR_GREED_SYNC_SOURCE,
                ticker=SENTIMENT_SYNC_TICKER,
                period="1y",
                interval="sentiment",
                status="failed",
                row_count=0,
                started_at=started_at,
                message=str(exc),
            )
            connection.commit()
            raise


def _recent_success_exists(connection, min_refresh_hours: int) -> bool:
    recent_runs = get_recent_sync_runs(
        connection,
        ticker=SENTIMENT_SYNC_TICKER,
        limit=20,
    )
    if recent_runs.empty:
        return False

    threshold = datetime.now(UTC) - timedelta(hours=min_refresh_hours)
    for row in recent_runs.to_dict("records"):
        if (
            row.get("source") != CNN_FEAR_GREED_SYNC_SOURCE
            or row.get("status") != "success"
            or row.get("period") != "1y"
        ):
            continue
        finished_at = pd_to_datetime_utc(row.get("finished_at"))
        if finished_at is not None and finished_at >= threshold:
            return True
    return False


def pd_to_datetime_utc(value) -> datetime | None:
    try:
        import pandas as pd

        parsed = pd.to_datetime(value, errors="coerce", utc=True)
    except Exception:
        return None

    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
