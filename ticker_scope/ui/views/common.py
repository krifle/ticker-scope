from __future__ import annotations

import streamlit as st

from ticker_scope.formatting import (
    format_date_range,
    format_optional_days,
    latest_sync_label,
)


def render_storage_summary(storage_status: dict[str, object]) -> None:
    summary = storage_status["summary"]
    coverage = storage_status["coverage"]
    recent_sync_runs = storage_status["recent_sync_runs"]

    db1, db2, db3, db4 = st.columns(4)
    db1.metric("DB price rows", f"{summary['daily_prices']:,}")
    db2.metric("Data range", format_date_range(coverage.start_date, coverage.end_date))
    db3.metric("Last sync", latest_sync_label(recent_sync_runs))
    db4.metric("Freshness", format_optional_days(coverage.freshness_days))
