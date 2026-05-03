from __future__ import annotations

import pandas as pd
import streamlit as st

from ticker_scope.formatting import format_horizon_label, format_metric
from ticker_scope.modeling.backtest import (
    make_holdout_metrics_frame,
    run_holdout_backtest,
    run_rolling_backtest,
    summarize_rolling_metrics,
)
from ticker_scope.services.storage import (
    load_saved_backtest_metrics,
    save_backtest_result,
)
from ticker_scope.ui.charts import (
    make_backtest_chart,
    make_backtest_comparison_chart,
    make_rolling_backtest_chart,
)
from ticker_scope.ui.helpers import make_saved_backtest_summary, rolling_state_key


def render_single_backtest_tab(
    symbol: str,
    period: str,
    prophet_df: pd.DataFrame,
    active_holidays: pd.DataFrame | None,
    interval_width: float,
    use_events: bool,
    date_policy: str,
    run_backtest: bool,
) -> None:
    if not run_backtest:
        st.empty()
        return

    backtest_mode = st.radio(
        "Backtest mode",
        ["Holdout", "Rolling"],
        horizontal=True,
    )
    event_count = 0 if active_holidays is None else len(active_holidays)

    if backtest_mode == "Holdout":
        backtest_result, metrics = run_holdout_backtest(
            prophet_df,
            train_ratio=0.8,
            holidays=active_holidays,
            interval_width=interval_width,
        )
        holdout_metrics = make_holdout_metrics_frame(
            prophet_df,
            metrics,
            train_ratio=0.8,
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("MAE", format_metric(metrics["mae"]))
        m2.metric("RMSE", format_metric(metrics["rmse"]))
        m3.metric("MAPE", format_metric(metrics["mape"], "%"))
        m4.metric("Coverage", format_metric(metrics["coverage"], "%"))
        st.plotly_chart(make_backtest_chart(backtest_result), width="stretch")

        if st.button("Save holdout result"):
            run_id = save_backtest_result(
                symbol=symbol,
                period=period,
                strategy="holdout",
                prophet_df=prophet_df,
                metrics=holdout_metrics,
                interval_width=interval_width,
                use_events=use_events,
                event_count=event_count,
                date_policy=date_policy,
                train_ratio=0.8,
            )
            st.success(f"Saved backtest run #{run_id}.")

        st.dataframe(backtest_result, width="stretch", hide_index=True)
    else:
        render_single_rolling_backtest(
            symbol=symbol,
            period=period,
            prophet_df=prophet_df,
            active_holidays=active_holidays,
            interval_width=interval_width,
            use_events=use_events,
            date_policy=date_policy,
            event_count=event_count,
        )

    render_saved_backtest_comparison(symbol)


def render_single_rolling_backtest(
    symbol: str,
    period: str,
    prophet_df: pd.DataFrame,
    active_holidays: pd.DataFrame | None,
    interval_width: float,
    use_events: bool,
    date_policy: str,
    event_count: int,
) -> None:
    control_left, control_middle, control_right = st.columns(3)
    with control_left:
        horizons = st.multiselect(
            "Horizons",
            [7, 14, 30, 60, 90, 180],
            default=[7, 30, 90],
        )
    with control_middle:
        rolling_windows = st.slider(
            "Rolling cutoffs",
            min_value=2,
            max_value=12,
            value=4,
            step=1,
        )
    with control_right:
        max_train_rows = max(30, len(prophet_df) - 2)
        default_min_train_rows = min(
            max_train_rows,
            min(504, max(60, len(prophet_df) // 2)),
        )
        min_train_rows = st.number_input(
            "Minimum train rows",
            min_value=30,
            max_value=max_train_rows,
            value=default_min_train_rows,
            step=21,
        )

    save_results = st.checkbox("Save rolling result to DB", value=True)
    normalized_horizons = sorted({int(horizon) for horizon in horizons})
    if not normalized_horizons:
        st.warning("Select at least one horizon.")
    state_key = rolling_state_key(
        symbol=symbol,
        period=period,
        interval_width=interval_width,
        use_events=use_events,
        date_policy=date_policy,
        horizons=normalized_horizons,
        rolling_windows=int(rolling_windows),
        min_train_rows=int(min_train_rows),
    )

    if st.button(
        "Run rolling backtest",
        type="primary",
        disabled=not normalized_horizons,
    ):
        rolling_result, rolling_metrics = run_rolling_backtest(
            prophet_df,
            horizons_days=normalized_horizons,
            rolling_windows=int(rolling_windows),
            min_train_rows=int(min_train_rows),
            holidays=active_holidays,
            interval_width=interval_width,
        )
        run_id = None
        if save_results:
            run_id = save_backtest_result(
                symbol=symbol,
                period=period,
                strategy="rolling",
                prophet_df=prophet_df,
                metrics=rolling_metrics,
                interval_width=interval_width,
                use_events=use_events,
                event_count=event_count,
                date_policy=date_policy,
                horizons_days=normalized_horizons,
                rolling_windows=int(rolling_windows),
                min_train_rows=int(min_train_rows),
            )
        st.session_state["rolling_backtest"] = {
            "key": state_key,
            "result": rolling_result,
            "metrics": rolling_metrics,
            "run_id": run_id,
        }

    rolling_state = st.session_state.get("rolling_backtest")
    if rolling_state is None or rolling_state.get("key") != state_key:
        st.info("Run rolling backtest to compare the selected horizons.")
        return

    rolling_result = rolling_state["result"]
    rolling_metrics = rolling_state["metrics"]
    if rolling_state.get("run_id") is not None:
        st.success(f"Saved backtest run #{rolling_state['run_id']}.")

    rolling_summary = summarize_rolling_metrics(rolling_metrics)
    if rolling_summary.empty:
        st.info("No rolling metrics were produced for this configuration.")
        return

    metric_cols = st.columns(4)
    best_row = rolling_summary.sort_values("mape").iloc[0]
    metric_cols[0].metric(
        "Best horizon",
        format_horizon_label(best_row["horizon_days"]),
    )
    metric_cols[1].metric("Best MAPE", format_metric(best_row["mape"], "%"))
    metric_cols[2].metric(
        "Avg coverage",
        format_metric(rolling_summary["coverage"].mean(), "%"),
    )
    metric_cols[3].metric("Samples", f"{int(rolling_summary['windows'].sum()):,}")

    st.subheader("Horizon performance")
    st.dataframe(rolling_summary, width="stretch", hide_index=True)

    selected_horizon = st.selectbox(
        "Chart horizon",
        normalized_horizons,
        format_func=lambda value: f"{value}d",
    )
    st.plotly_chart(
        make_rolling_backtest_chart(rolling_result, selected_horizon),
        width="stretch",
    )
    st.dataframe(rolling_metrics, width="stretch", hide_index=True)


def render_saved_backtest_comparison(symbol: str) -> None:
    st.subheader("Saved performance comparison")
    show_all_tickers = st.checkbox("Show all tickers", value=False)
    saved_metrics = load_saved_backtest_metrics(None if show_all_tickers else symbol)
    saved_summary = make_saved_backtest_summary(saved_metrics)
    if saved_summary.empty:
        st.info("No saved backtest results yet.")
        return

    comparison_metric = st.selectbox(
        "Comparison metric",
        ["mape", "mae", "rmse", "coverage"],
        index=0,
    )
    st.plotly_chart(
        make_backtest_comparison_chart(saved_summary, comparison_metric),
        width="stretch",
    )
    st.dataframe(saved_summary, width="stretch", hide_index=True)
