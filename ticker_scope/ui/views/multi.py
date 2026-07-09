from __future__ import annotations

import streamlit as st

from ticker_scope.date_policy import date_policy_label
from ticker_scope.formatting import format_metric
from ticker_scope.services.analysis import run_multi_ticker_analysis
from ticker_scope.services.storage import load_saved_backtest_metrics
from ticker_scope.ui.charts import (
    make_backtest_comparison_chart,
    make_multi_anomaly_chart,
    make_multi_metric_bar_chart,
)
from ticker_scope.ui.data_access import cached_history
from ticker_scope.ui.helpers import make_saved_backtest_summary, multi_state_key


def render_multi_ticker_view(
    symbols: list[str],
    period: str,
    forecast_days: int,
    interval_width: float,
    use_events: bool,
    date_policy: str,
    force_refresh: bool,
) -> None:
    st.subheader("Multi ticker comparison")
    if not symbols:
        st.warning("Select at least one ticker.")
        return

    save_results = st.checkbox("Save holdout metrics to DB", value=False)
    state_key = multi_state_key(
        symbols=symbols,
        period=period,
        forecast_days=forecast_days,
        interval_width=interval_width,
        use_events=use_events,
        save_results=save_results,
        date_policy=date_policy,
    )
    run_clicked = st.button("Run multi-ticker analysis", type="primary")

    if run_clicked or force_refresh:
        with st.spinner("Running multi-ticker analysis..."):
            progress = st.progress(0.0)
            status_text = st.empty()
            try:
                st.session_state["multi_ticker_analysis"] = {
                    "key": state_key,
                    "result": run_multi_ticker_analysis(
                        symbols=symbols,
                        period=period,
                        forecast_days=forecast_days,
                        interval_width=interval_width,
                        use_events=use_events,
                        date_policy=date_policy,
                        force_refresh=force_refresh,
                        save_results=save_results,
                        history_loader=cached_history,
                        progress_callback=lambda index, total: progress.progress(
                            index / total
                        ),
                        status_callback=lambda symbol, index, total: status_text.caption(
                            f"Analyzing {symbol} ({index}/{total})"
                        ),
                    ),
                }
            finally:
                progress.empty()
                status_text.empty()

    state = st.session_state.get("multi_ticker_analysis")
    if state is None or state.get("key") != state_key:
        st.info("Run multi-ticker analysis to sync data and compare selected tickers.")
        return

    result = state["result"]
    summary = result["summary"]
    anomalies = result["anomalies"]
    errors = result["errors"]

    if not errors.empty:
        st.warning("Some tickers could not be analyzed.")
        st.dataframe(errors, width="stretch", hide_index=True)

    if summary.empty:
        st.info("No successful ticker analysis results.")
        return

    best_row = summary.sort_values("mape").iloc[0]
    anomaly_row = summary.sort_values("anomaly_rate_pct", ascending=False).iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tickers", f"{len(summary):,}")
    c2.metric(
        "Best MAPE",
        f"{best_row['ticker_label']} · {format_metric(best_row['mape'], '%')}",
    )
    c3.metric(
        "Highest anomaly rate",
        (
            f"{anomaly_row['ticker_label']} · "
            f"{format_metric(anomaly_row['anomaly_rate_pct'], '%')}"
        ),
    )
    c4.metric("Fetched rows", f"{int(summary['fetched_rows'].sum()):,}")
    st.caption(
        f"Data range: {summary['data_start_date'].min()} ~ "
        f"{summary['latest_date'].max()} · "
        f"Date handling: {date_policy_label(date_policy)}"
    )

    tabs = st.tabs(["Performance", "Anomalies", "Sync/Data", "Saved Backtests"])

    with tabs[0]:
        metric = st.selectbox(
            "Metric",
            ["mape", "mae", "rmse", "coverage"],
            index=0,
        )
        st.plotly_chart(make_multi_metric_bar_chart(summary, metric), width="stretch")
        st.dataframe(
            summary.sort_values("mape"),
            width="stretch",
            hide_index=True,
        )

    with tabs[1]:
        st.plotly_chart(make_multi_anomaly_chart(summary), width="stretch")
        if anomalies.empty:
            st.info("No anomaly points detected.")
        else:
            st.dataframe(
                anomalies[
                    [
                        "ticker",
                        "ticker_label",
                        "ds",
                        "y",
                        "yhat",
                        "expected_range",
                        "direction",
                        "bound_exceeded",
                        "distance_from_bound",
                        "distance_from_bound_pct",
                        "error_pct",
                        "explanation",
                    ]
                ].head(200),
                width="stretch",
                hide_index=True,
            )

    with tabs[2]:
        st.dataframe(
            summary[
                [
                    "ticker",
                    "ticker_label",
                    "rows",
                    "fetched_rows",
                    "data_start_date",
                    "latest_date",
                    "latest_close",
                    "last_sync_at",
                    "event_count",
                    "date_policy",
                    "sync_message",
                    "saved_run_id",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

    with tabs[3]:
        saved_metrics = load_saved_backtest_metrics(None)
        if not saved_metrics.empty:
            saved_metrics = saved_metrics[saved_metrics["ticker"].isin(symbols)]
        saved_summary = make_saved_backtest_summary(saved_metrics)
        if saved_summary.empty:
            st.info("No saved backtest results for the selected tickers yet.")
        else:
            comparison_metric = st.selectbox(
                "Saved comparison metric",
                ["mape", "mae", "rmse", "coverage"],
                index=0,
            )
            st.plotly_chart(
                make_backtest_comparison_chart(saved_summary, comparison_metric),
                width="stretch",
            )
            st.dataframe(saved_summary, width="stretch", hide_index=True)
