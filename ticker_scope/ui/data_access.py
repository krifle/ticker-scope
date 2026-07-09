from __future__ import annotations

import streamlit as st

from ticker_scope.data.database import get_connection, init_database
from ticker_scope.data.repositories import (
    get_fear_greed_coverage,
    get_fear_greed_history,
    get_recent_sync_runs,
    list_fear_greed_values,
)
from ticker_scope.data.sync import SyncResult, sync_price_history
from ticker_scope.observability import get_logger
from ticker_scope.sentiment.sync import SENTIMENT_SYNC_TICKER


LOGGER = get_logger(__name__)


@st.cache_data(ttl=900, show_spinner=False)
def cached_history(
    symbol: str,
    period: str,
    force_refresh: bool,
    date_policy: str,
) -> SyncResult:
    return sync_price_history(
        symbol=symbol,
        period=period,
        interval="1d",
        auto_adjust=True,
        force_refresh=force_refresh,
        date_policy=date_policy,
    )


def clear_cached_history() -> None:
    cached_history.clear()
    cached_fear_greed_history.clear()
    cached_fear_greed_status.clear()


@st.cache_data(ttl=900, show_spinner=False)
def cached_fear_greed_history(start_date=None, end_date=None):
    init_database()
    with get_connection() as connection:
        history = get_fear_greed_history(
            connection,
            start_date=start_date,
            end_date=end_date,
        )
    LOGGER.info(
        "DB read table=fear_greed_index rows=%s start_date=%s end_date=%s",
        len(history),
        start_date,
        end_date,
    )
    return history


@st.cache_data(ttl=300, show_spinner=False)
def cached_fear_greed_status():
    init_database()
    with get_connection() as connection:
        coverage = get_fear_greed_coverage(connection)
        recent_sync_runs = get_recent_sync_runs(
            connection,
            ticker=SENTIMENT_SYNC_TICKER,
            limit=10,
        )
        values = list_fear_greed_values(connection, limit=500)
    LOGGER.info(
        "DB read fear_greed_status coverage_rows=%s recent_sync_runs=%s values=%s",
        coverage["row_count"],
        len(recent_sync_runs),
        len(values),
    )
    return {
        "coverage": coverage,
        "recent_sync_runs": recent_sync_runs,
        "values": values,
    }


def clear_cached_fear_greed() -> None:
    cached_fear_greed_history.clear()
    cached_fear_greed_status.clear()
