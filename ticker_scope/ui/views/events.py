from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ticker_scope.data.repositories import EVENT_CATEGORIES
from ticker_scope.events.providers import ALPHA_VANTAGE_HORIZONS
from ticker_scope.events.sync import sync_earnings_events
from ticker_scope.services.storage import remove_event, save_manual_event
from ticker_scope.ui.charts import make_event_comparison_chart
from ticker_scope.ui.helpers import event_option_label, make_event_comparison_table


def render_events_tab(
    symbol: str,
    events: pd.DataFrame,
    prophet_df: pd.DataFrame,
    baseline_forecast: pd.DataFrame | None,
    event_forecast: pd.DataFrame,
) -> None:
    st.subheader("External earnings calendar")
    api_left, api_middle, api_right = st.columns([2, 1, 1])
    with api_left:
        alpha_vantage_key = st.text_input(
            "Alpha Vantage API key",
            value="",
            type="password",
            placeholder="Uses ALPHA_VANTAGE_API_KEY when empty",
        )
    with api_middle:
        earnings_horizon = st.selectbox(
            "Horizon",
            ALPHA_VANTAGE_HORIZONS,
            index=0,
        )
    with api_right:
        force_event_sync = st.checkbox("Force API refresh", value=False)

    if st.button("Sync earnings events"):
        try:
            result = sync_earnings_events(
                symbol=symbol,
                horizon=earnings_horizon,
                api_key=alpha_vantage_key,
                force_refresh=force_event_sync,
            )
            if result.from_cache:
                st.info(result.message)
            else:
                st.success(f"{result.message}; fetched {result.fetched_rows} rows.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.subheader("Manual event")

    with st.form("manual-event-form", clear_on_submit=True):
        left, right = st.columns(2)
        with left:
            event_name = st.text_input("Event name", value="")
            event_date = st.date_input("Date", value=date.today())
            event_category = st.selectbox(
                "Category",
                EVENT_CATEGORIES,
                index=EVENT_CATEGORIES.index("manual"),
            )
            event_ticker = st.text_input("Ticker", value=symbol)
        with right:
            lower_window = st.number_input(
                "Lower window",
                min_value=-30,
                max_value=0,
                value=0,
                step=1,
            )
            upper_window = st.number_input(
                "Upper window",
                min_value=0,
                max_value=30,
                value=0,
                step=1,
            )
            notes = st.text_area("Notes", value="", height=116)

        submitted = st.form_submit_button("Save event")

    if submitted:
        try:
            save_manual_event(
                name=event_name,
                event_date=event_date,
                category=event_category,
                ticker=event_ticker,
                lower_window=int(lower_window),
                upper_window=int(upper_window),
                notes=notes,
            )
            st.success("Event saved.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.subheader("Registered events")
    if events.empty:
        st.info("No events registered for this ticker yet.")
    else:
        display_events = events[
            [
                "id",
                "event_date",
                "ticker",
                "category",
                "name",
                "lower_window",
                "upper_window",
                "source",
                "notes",
            ]
        ].copy()
        display_events["ticker"] = display_events["ticker"].fillna("GLOBAL")
        st.dataframe(display_events, width="stretch", hide_index=True)

        event_ids = events["id"].astype(int).tolist()
        delete_id = st.selectbox(
            "Delete event",
            event_ids,
            format_func=lambda event_id: event_option_label(events, event_id),
        )
        if st.button("Delete selected event"):
            remove_event(delete_id)
            st.success("Event deleted.")
            st.rerun()

    st.subheader("Forecast comparison")
    if baseline_forecast is None:
        st.info("Register at least one event to compare forecasts with and without events.")
        return

    st.plotly_chart(
        make_event_comparison_chart(
            prophet_df,
            baseline_forecast,
            event_forecast,
            events=events,
        ),
        width="stretch",
    )

    comparison = make_event_comparison_table(
        baseline_forecast,
        event_forecast,
        latest_date=prophet_df.iloc[-1]["ds"].date(),
    )
    st.dataframe(comparison, width="stretch", hide_index=True)
