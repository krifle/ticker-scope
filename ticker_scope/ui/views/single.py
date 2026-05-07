from __future__ import annotations

import streamlit as st

from ticker_scope.date_policy import date_policy_label
from ticker_scope.data.market_data import to_prophet_frame
from ticker_scope.events.calendar import events_to_holidays
from ticker_scope.modeling.anomalies import anomaly_summary, detect_interval_anomalies
from ticker_scope.modeling.prophet_model import fit_and_forecast
from ticker_scope.services.storage import load_model_events, load_storage_status
from ticker_scope.ui.charts import (
    make_components_chart,
    make_forecast_chart,
)
from ticker_scope.ui.data_access import cached_history
from ticker_scope.ui.data_access import cached_fear_greed_history
from ticker_scope.ui.helpers import prepare_anomaly_table
from ticker_scope.ui.views.backtest import render_single_backtest_tab
from ticker_scope.ui.views.common import render_storage_summary
from ticker_scope.ui.views.data import render_data_tab
from ticker_scope.ui.views.events import render_events_tab
from ticker_scope.ui.views.sentiment import render_sentiment_tab


def render_single_ticker_view(
    symbol: str,
    period: str,
    forecast_days: int,
    interval_width: float,
    use_events: bool,
    date_policy: str,
    run_backtest: bool,
    force_refresh: bool,
) -> None:
    sync_result = cached_history(symbol, period, force_refresh)
    db_events = load_model_events(symbol)
    db_event_holidays = events_to_holidays(db_events)
    active_holidays = db_event_holidays if use_events else None
    history = sync_result.history
    prophet_df = to_prophet_frame(history)
    storage_status = load_storage_status(symbol, period, date_policy)
    _, forecast = fit_and_forecast(
        prophet_df,
        periods=forecast_days,
        holidays=active_holidays,
        interval_width=interval_width,
        date_policy=date_policy,
    )
    baseline_forecast = None
    comparison_event_forecast = forecast
    if db_event_holidays is not None and not db_event_holidays.empty:
        if use_events:
            _, baseline_forecast = fit_and_forecast(
                prophet_df,
                periods=forecast_days,
                holidays=None,
                interval_width=interval_width,
                date_policy=date_policy,
            )
        else:
            baseline_forecast = forecast
            _, comparison_event_forecast = fit_and_forecast(
                prophet_df,
                periods=forecast_days,
                holidays=db_event_holidays,
                interval_width=interval_width,
                date_policy=date_policy,
            )
    anomalies = detect_interval_anomalies(prophet_df, forecast)
    anomaly_points = anomaly_summary(anomalies)
    fear_greed = cached_fear_greed_history(
        start_date=prophet_df["ds"].min().date(),
        end_date=forecast["ds"].max().date(),
    )

    latest_price = prophet_df.iloc[-1]["y"]
    latest_date = prophet_df.iloc[-1]["ds"].date()
    anomaly_count = int(anomalies["is_anomaly"].sum())

    col1, col2, col3 = st.columns(3)
    col1.metric("Latest close", f"{latest_price:,.2f}")
    col2.metric("Latest date", str(latest_date))
    col3.metric("Anomalies", f"{anomaly_count:,}")
    render_storage_summary(storage_status)
    st.caption(
        f"Local DB: {sync_result.message} "
        f"({len(history):,} rows available, fetched {sync_result.fetched_rows:,}) · "
        f"Events used: {0 if active_holidays is None else len(active_holidays):,} · "
        f"Date handling: {date_policy_label(date_policy)}"
    )

    tabs = st.tabs(["Forecast", "Anomalies", "Backtest", "Events", "Sentiment", "Data"])

    with tabs[0]:
        st.plotly_chart(
            make_forecast_chart(
                prophet_df,
                forecast,
                anomalies,
                events=db_events if active_holidays is not None else None,
                fear_greed=fear_greed,
            ),
            width="stretch",
        )
        st.subheader("Prophet components")
        st.plotly_chart(make_components_chart(forecast), width="stretch")

    with tabs[1]:
        if anomaly_points.empty:
            st.info("No anomaly points detected.")
        else:
            st.dataframe(
                prepare_anomaly_table(anomaly_points),
                width="stretch",
                hide_index=True,
            )

    with tabs[2]:
        render_single_backtest_tab(
            symbol=symbol,
            period=period,
            prophet_df=prophet_df,
            active_holidays=active_holidays,
            interval_width=interval_width,
            use_events=use_events,
            date_policy=date_policy,
            run_backtest=run_backtest,
        )

    with tabs[3]:
        render_events_tab(
            symbol=symbol,
            events=db_events,
            prophet_df=prophet_df,
            baseline_forecast=baseline_forecast,
            event_forecast=comparison_event_forecast,
        )

    with tabs[4]:
        render_sentiment_tab()

    with tabs[5]:
        render_data_tab(symbol, period, history, date_policy, storage_status)
