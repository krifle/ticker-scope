from __future__ import annotations

import pandas as pd
import streamlit as st

from ticker_scope.data.database import resolve_db_path
from ticker_scope.formatting import format_date_range, format_optional_number
from ticker_scope.services.storage import load_storage_status


def render_data_tab(
    symbol: str,
    period: str,
    history: pd.DataFrame,
    date_policy: str,
    storage_status: dict[str, object] | None = None,
) -> None:
    if storage_status is None:
        storage_status = load_storage_status(symbol, period, date_policy)
    summary = storage_status["summary"]
    coverage = storage_status["coverage"]

    st.subheader("Local storage")
    st.caption(str(resolve_db_path()))

    db1, db2, db3, db4, db5, db6 = st.columns(6)
    db1.metric("Stored price rows", f"{summary['daily_prices']:,}")
    db2.metric("Symbols", f"{summary['symbols']:,}")
    db3.metric("Sync runs", f"{summary['sync_runs']:,}")
    db4.metric("Events", f"{summary['events']:,}")
    db5.metric("Backtests", f"{summary['backtest_runs']:,}")
    db6.metric("Sentiment", f"{summary['fear_greed_index']:,}")

    cv1, cv2, cv3, cv4 = st.columns(4)
    cv1.metric("Selected rows", f"{coverage.row_count:,}")
    cv2.metric("Stored range", format_date_range(coverage.start_date, coverage.end_date))
    cv3.metric("Freshness days", format_optional_number(coverage.freshness_days))
    cv4.metric(
        "Longest gap",
        f"{coverage.longest_missing_business_day_run:,} expected days",
    )

    st.subheader("Recent sync runs")
    st.dataframe(storage_status["recent_sync_runs"], width="stretch", hide_index=True)

    st.subheader("Price history")
    st.dataframe(history, width="stretch", hide_index=True)
