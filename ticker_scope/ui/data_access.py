from __future__ import annotations

import streamlit as st

from ticker_scope.data.sync import SyncResult, sync_price_history


@st.cache_data(ttl=900, show_spinner=False)
def cached_history(symbol: str, period: str, force_refresh: bool) -> SyncResult:
    return sync_price_history(
        symbol=symbol,
        period=period,
        interval="1d",
        auto_adjust=True,
        force_refresh=force_refresh,
    )


def clear_cached_history() -> None:
    cached_history.clear()
