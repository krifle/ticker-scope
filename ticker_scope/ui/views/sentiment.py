from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ticker_scope.data.database import get_connection, init_database
from ticker_scope.data.repositories import (
    classify_fear_greed_value,
    delete_fear_greed_value,
    upsert_fear_greed_index,
)
from ticker_scope.formatting import format_date_range, latest_sync_label
from ticker_scope.observability import get_logger
from ticker_scope.sentiment.sync import sync_fear_greed_index
from ticker_scope.ui.data_access import (
    cached_fear_greed_status,
    clear_cached_fear_greed,
)


LOGGER = get_logger(__name__)


def render_sentiment_tab() -> None:
    status = cached_fear_greed_status()
    coverage = status["coverage"]
    recent_sync_runs = status["recent_sync_runs"]
    values = status["values"]

    st.subheader("Fear & Greed Index")
    m1, m2, m3, m4 = st.columns(4)
    latest_value = coverage["latest_value"]
    m1.metric(
        "Latest value",
        "-" if latest_value is None else f"{latest_value:.0f}",
    )
    m2.metric("Classification", coverage["latest_classification"] or "-")
    m3.metric(
        "Stored range",
        format_date_range(coverage["start_date"], coverage["end_date"]),
    )
    m4.metric("Last sync", latest_sync_label(recent_sync_runs))

    c1, c2 = st.columns([1, 1])
    with c1:
        force_refresh = st.checkbox(
            "Force API refresh",
            value=False,
            key="sentiment_force_api_refresh",
        )
    with c2:
        if st.button(
            "Sync CNN Fear & Greed",
            width="stretch",
            key="sentiment_sync_cnn_fear_greed",
        ):
            try:
                result = sync_fear_greed_index(force_refresh=force_refresh)
                clear_cached_fear_greed()
                st.success(result.message)
            except Exception as exc:
                clear_cached_fear_greed()
                st.error(str(exc))

    _render_manual_entry_form()
    _render_csv_import_form()
    _render_delete_form(values)

    st.subheader("Stored sentiment values")
    if values.empty:
        st.info("No Fear & Greed values saved yet.")
    else:
        st.dataframe(values, width="stretch", hide_index=True)

    st.subheader("Recent sentiment sync runs")
    st.dataframe(recent_sync_runs, width="stretch", hide_index=True)


def _render_manual_entry_form() -> None:
    st.subheader("Manual entry")
    with st.form("manual_fear_greed_form"):
        entry_date = st.date_input("Date", value=date.today())
        value = st.number_input(
            "Value",
            min_value=0.0,
            max_value=100.0,
            value=50.0,
            step=1.0,
        )
        classification = classify_fear_greed_value(float(value))
        st.caption(f"Classification: {classification}")
        notes = st.text_input("Notes", value="")
        submitted = st.form_submit_button("Save manual value")

    if not submitted:
        return

    data = pd.DataFrame(
        [
            {
                "index_date": entry_date,
                "value": float(value),
                "classification": classification,
                "notes": notes,
            }
        ]
    )
    init_database()
    with get_connection() as connection:
        stored_rows = upsert_fear_greed_index(connection, data, source="manual")
        connection.commit()
    LOGGER.info(
        "DB write table=fear_greed_index source=manual rows=%s index_date=%s",
        stored_rows,
        entry_date,
    )
    clear_cached_fear_greed()
    st.success(f"Saved {stored_rows} manual Fear & Greed value.")


def _render_csv_import_form() -> None:
    st.subheader("CSV import")
    uploaded = st.file_uploader(
        "Upload CSV",
        type=["csv"],
        help="Required columns: date,value. Optional columns: classification,notes.",
        key="sentiment_csv_upload",
    )
    if uploaded is None:
        return

    try:
        csv_data = pd.read_csv(uploaded)
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")
        return

    if st.button("Import CSV values", key="sentiment_import_csv_values"):
        init_database()
        with get_connection() as connection:
            stored_rows = upsert_fear_greed_index(
                connection,
                csv_data,
                source="csv_import",
            )
            connection.commit()
        LOGGER.info(
            "DB write table=fear_greed_index source=csv_import rows=%s",
            stored_rows,
        )
        clear_cached_fear_greed()
        st.success(f"Imported {stored_rows} Fear & Greed values.")


def _render_delete_form(values: pd.DataFrame) -> None:
    if values.empty:
        return

    st.subheader("Delete value")
    value_ids = [int(value_id) for value_id in values["id"].dropna().tolist()]
    if not value_ids:
        return

    selected_id = st.selectbox("Value ID", value_ids, key="sentiment_delete_value_id")
    if st.button("Delete selected value", key="sentiment_delete_selected_value"):
        init_database()
        with get_connection() as connection:
            deleted = delete_fear_greed_value(connection, int(selected_id))
            connection.commit()
        LOGGER.info(
            "DB write table=fear_greed_index delete value_id=%s deleted=%s",
            selected_id,
            deleted,
        )
        clear_cached_fear_greed()
        if deleted:
            st.success(f"Deleted Fear & Greed value #{selected_id}.")
        else:
            st.warning("Selected value was not found.")
