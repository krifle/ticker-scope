from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ticker_scope.date_policy import DATE_POLICY_OPTIONS, date_policy_label
from ticker_scope.data.database import get_connection, init_database, resolve_db_path
from ticker_scope.data.market_data import (
    DEFAULT_SYMBOLS,
    to_prophet_frame,
)
from ticker_scope.data.repositories import (
    EVENT_CATEGORIES,
    add_event,
    delete_event,
    get_database_summary,
    get_price_coverage,
    get_recent_sync_runs,
    list_backtest_metrics,
    list_events,
    record_backtest_metrics,
    record_backtest_run,
)
from ticker_scope.data.sync import period_to_start_date, sync_price_history
from ticker_scope.events.calendar import events_to_holidays
from ticker_scope.events.providers import ALPHA_VANTAGE_HORIZONS
from ticker_scope.events.sync import sync_earnings_events
from ticker_scope.modeling.anomalies import anomaly_summary, detect_interval_anomalies
from ticker_scope.modeling.backtest import (
    make_holdout_metrics_frame,
    run_holdout_backtest,
    run_rolling_backtest,
    summarize_rolling_metrics,
)
from ticker_scope.modeling.prophet_model import fit_and_forecast
from ticker_scope.ui.charts import (
    make_backtest_chart,
    make_backtest_comparison_chart,
    make_components_chart,
    make_event_comparison_chart,
    make_forecast_chart,
    make_multi_anomaly_chart,
    make_multi_metric_bar_chart,
    make_rolling_backtest_chart,
)


st.set_page_config(page_title="Ticker Scope", layout="wide")


@st.cache_data(ttl=900, show_spinner=False)
def cached_history(symbol: str, period: str, force_refresh: bool):
    return sync_price_history(
        symbol=symbol,
        period=period,
        interval="1d",
        auto_adjust=True,
        force_refresh=force_refresh,
    )


def load_storage_status(symbol: str, period: str, date_policy: str):
    init_database()
    with get_connection() as connection:
        return {
            "summary": get_database_summary(connection),
            "coverage": get_price_coverage(
                connection,
                ticker=symbol,
                start_date=period_to_start_date(period),
                end_date=date.today(),
                interval="1d",
                adjusted=True,
                date_policy=date_policy,
            ),
            "recent_sync_runs": get_recent_sync_runs(connection, ticker=symbol, limit=20),
        }


def load_model_events(symbol: str) -> pd.DataFrame:
    init_database()
    with get_connection() as connection:
        return list_events(connection, ticker=symbol, include_global=True)


def load_saved_backtest_metrics(symbol: str | None) -> pd.DataFrame:
    init_database()
    with get_connection() as connection:
        return list_backtest_metrics(connection, ticker=symbol, limit=1000)


def load_latest_sync_run(symbol: str) -> pd.Series | None:
    init_database()
    with get_connection() as connection:
        recent_runs = get_recent_sync_runs(connection, ticker=symbol, limit=1)
    if recent_runs.empty:
        return None
    return recent_runs.iloc[0]


def save_backtest_result(
    symbol: str,
    period: str,
    strategy: str,
    prophet_df: pd.DataFrame,
    metrics: pd.DataFrame,
    interval_width: float,
    use_events: bool,
    event_count: int,
    date_policy: str,
    train_ratio: float | None = None,
    horizons_days: list[int] | None = None,
    rolling_windows: int | None = None,
    min_train_rows: int | None = None,
) -> int:
    with get_connection() as connection:
        run_id = record_backtest_run(
            connection,
            ticker=symbol,
            strategy=strategy,
            period=period,
            interval="1d",
            adjusted=True,
            train_ratio=train_ratio,
            horizons_days=horizons_days,
            rolling_windows=rolling_windows,
            min_train_rows=min_train_rows,
            interval_width=interval_width,
            use_events=use_events,
            event_count=event_count,
            date_policy=date_policy,
            row_count=len(prophet_df),
            data_start_date=prophet_df.iloc[0]["ds"],
            data_end_date=prophet_df.iloc[-1]["ds"],
        )
        record_backtest_metrics(connection, run_id, metrics)
        connection.commit()
    return run_id


def save_manual_event(
    name: str,
    event_date: date,
    category: str,
    ticker: str,
    lower_window: int,
    upper_window: int,
    notes: str,
) -> None:
    with get_connection() as connection:
        add_event(
            connection,
            name=name,
            event_date=event_date,
            category=category,
            ticker=ticker,
            lower_window=lower_window,
            upper_window=upper_window,
            notes=notes,
        )
        connection.commit()


def remove_event(event_id: int) -> None:
    with get_connection() as connection:
        delete_event(connection, event_id)
        connection.commit()


def _format_date_range(start_date, end_date) -> str:
    if start_date is None or end_date is None:
        return "-"
    return f"{start_date} ~ {end_date}"


def _format_optional_number(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value:,}"


def _format_optional_days(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value:,} days"


def _format_sync_time(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "-"
    return timestamp.tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M KST")


def _latest_sync_label(recent_sync_runs: pd.DataFrame) -> str:
    if recent_sync_runs.empty:
        return "-"
    row = recent_sync_runs.iloc[0]
    status = str(row.get("status", "-"))
    return f"{_format_sync_time(row.get('finished_at'))} · {status}"


def _prepare_anomaly_table(anomaly_points: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "ds",
        "y",
        "yhat",
        "expected_range",
        "direction",
        "bound_exceeded",
        "distance_from_bound",
        "distance_from_bound_pct",
        "error_pct",
        "interval_width_value",
        "explanation",
    ]
    available_columns = [column for column in columns if column in anomaly_points.columns]
    return anomaly_points[available_columns].head(100)


def render_storage_summary(storage_status: dict[str, object]) -> None:
    summary = storage_status["summary"]
    coverage = storage_status["coverage"]
    recent_sync_runs = storage_status["recent_sync_runs"]

    db1, db2, db3, db4 = st.columns(4)
    db1.metric("DB price rows", f"{summary['daily_prices']:,}")
    db2.metric("Data range", _format_date_range(coverage.start_date, coverage.end_date))
    db3.metric("Last sync", _latest_sync_label(recent_sync_runs))
    db4.metric("Freshness", _format_optional_days(coverage.freshness_days))


def _event_option_label(events: pd.DataFrame, event_id: int) -> str:
    row = events.loc[events["id"] == event_id].iloc[0]
    scope = row["ticker"] if pd.notna(row["ticker"]) else "GLOBAL"
    return f"{row['event_date']} | {scope} | {row['category']} | {row['name']}"


def make_event_comparison_table(
    baseline_forecast: pd.DataFrame,
    event_forecast: pd.DataFrame,
    latest_date: date,
) -> pd.DataFrame:
    comparison = baseline_forecast[["ds", "yhat"]].merge(
        event_forecast[["ds", "yhat"]],
        on="ds",
        suffixes=("_without_events", "_with_events"),
    )
    comparison["delta"] = (
        comparison["yhat_with_events"] - comparison["yhat_without_events"]
    )
    comparison["delta_pct"] = (
        comparison["delta"] / comparison["yhat_without_events"].abs() * 100
    )
    comparison = comparison[comparison["ds"].dt.date > latest_date]
    return comparison.sort_values("ds").reset_index(drop=True)


def make_saved_backtest_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return metrics.copy()

    grouped = (
        metrics.groupby(
            [
                "run_id",
                "ticker",
                "strategy",
                "period",
                "interval_width",
                "use_events",
                "event_count",
                "date_policy",
                "rolling_windows",
                "min_train_rows",
                "horizon_days",
                "run_created_at",
            ],
            dropna=False,
        )
        .agg(
            samples=("cutoff_date", "count"),
            test_rows=("test_rows", "sum"),
            mae=("mae", "mean"),
            rmse=("rmse", "mean"),
            mape=("mape", "mean"),
            coverage=("coverage", "mean"),
        )
        .reset_index()
    )
    grouped["horizon_label"] = grouped["horizon_days"].apply(_format_horizon_label)
    grouped["horizon_sort"] = grouped["horizon_days"].fillna(0).astype(int)
    grouped["run_label"] = grouped.apply(_make_run_label, axis=1)
    return grouped.sort_values(["run_id", "horizon_sort"], ascending=[False, True])


def _format_horizon_label(value) -> str:
    if pd.isna(value):
        return "Holdout"
    return f"{int(value)}d"


def _make_run_label(row: pd.Series) -> str:
    created_at = str(row["run_created_at"])[:16].replace("T", " ")
    event_label = "events" if bool(row["use_events"]) else "no events"
    date_label = date_policy_label(str(row.get("date_policy", "")))
    return (
        f"#{int(row['run_id'])} {row['ticker']} {row['strategy']} "
        f"{row['period']} {event_label} {date_label} {created_at}"
    )


def _format_metric(value: float, suffix: str = "") -> str:
    if pd.isna(value):
        return "-"
    return f"{value:,.2f}{suffix}"


def _rolling_state_key(
    symbol: str,
    period: str,
    interval_width: float,
    use_events: bool,
    date_policy: str,
    horizons: list[int],
    rolling_windows: int,
    min_train_rows: int,
) -> str:
    horizon_part = ",".join(str(horizon) for horizon in horizons)
    return (
        f"{symbol}:{period}:{interval_width:.2f}:{use_events}:{date_policy}:"
        f"{horizon_part}:{rolling_windows}:{min_train_rows}"
    )


def _normalize_symbol_list(
    preset_symbols: list[str],
    custom_symbols_text: str,
) -> list[str]:
    custom_symbols = [
        item.strip().upper()
        for item in custom_symbols_text.replace("\n", ",").split(",")
        if item.strip()
    ]
    return list(dict.fromkeys([*preset_symbols, *custom_symbols]))


def _multi_state_key(
    symbols: list[str],
    period: str,
    forecast_days: int,
    interval_width: float,
    use_events: bool,
    save_results: bool,
    date_policy: str,
) -> str:
    symbol_part = ",".join(symbols)
    return (
        f"{symbol_part}:{period}:{forecast_days}:"
        f"{interval_width:.2f}:{use_events}:{save_results}:{date_policy}"
    )


def run_multi_ticker_analysis(
    symbols: list[str],
    period: str,
    forecast_days: int,
    interval_width: float,
    use_events: bool,
    date_policy: str,
    force_refresh: bool,
    save_results: bool,
) -> dict[str, pd.DataFrame]:
    summary_rows = []
    anomaly_frames = []
    error_rows = []

    progress = st.progress(0.0)
    status_text = st.empty()
    total_symbols = len(symbols)

    for index, symbol in enumerate(symbols, start=1):
        status_text.caption(f"Analyzing {symbol} ({index}/{total_symbols})")
        try:
            row, anomalies = analyze_ticker_for_comparison(
                symbol=symbol,
                period=period,
                forecast_days=forecast_days,
                interval_width=interval_width,
                use_events=use_events,
                date_policy=date_policy,
                force_refresh=force_refresh,
                save_results=save_results,
            )
            summary_rows.append(row)
            if not anomalies.empty:
                anomaly_frames.append(anomalies)
        except Exception as exc:
            error_rows.append({"ticker": symbol, "error": str(exc)})
        finally:
            progress.progress(index / total_symbols)

    progress.empty()
    status_text.empty()

    return {
        "summary": pd.DataFrame(summary_rows),
        "anomalies": (
            pd.concat(anomaly_frames, ignore_index=True)
            if anomaly_frames
            else pd.DataFrame()
        ),
        "errors": pd.DataFrame(error_rows),
    }


def analyze_ticker_for_comparison(
    symbol: str,
    period: str,
    forecast_days: int,
    interval_width: float,
    use_events: bool,
    date_policy: str,
    force_refresh: bool,
    save_results: bool,
) -> tuple[dict[str, object], pd.DataFrame]:
    sync_result = cached_history(symbol, period, force_refresh)
    latest_sync = load_latest_sync_run(symbol)
    events = load_model_events(symbol)
    holidays = events_to_holidays(events)
    active_holidays = holidays if use_events else None
    event_count = 0 if active_holidays is None else len(active_holidays)

    prophet_df = to_prophet_frame(sync_result.history)
    _, forecast = fit_and_forecast(
        prophet_df,
        periods=forecast_days,
        holidays=active_holidays,
        interval_width=interval_width,
        date_policy=date_policy,
    )
    anomalies = detect_interval_anomalies(prophet_df, forecast)
    anomaly_points = anomaly_summary(anomalies).copy()
    if not anomaly_points.empty:
        anomaly_points.insert(0, "ticker", symbol)

    _, metrics = run_holdout_backtest(
        prophet_df,
        train_ratio=0.8,
        holidays=active_holidays,
        interval_width=interval_width,
    )
    run_id = None
    if save_results:
        holdout_metrics = make_holdout_metrics_frame(
            prophet_df,
            metrics,
            train_ratio=0.8,
        )
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

    anomaly_count = int(anomalies["is_anomaly"].sum())
    row_count = len(prophet_df)
    return (
        {
            "ticker": symbol,
            "rows": row_count,
            "fetched_rows": sync_result.fetched_rows,
            "latest_date": prophet_df.iloc[-1]["ds"].date(),
            "data_start_date": prophet_df.iloc[0]["ds"].date(),
            "latest_close": float(prophet_df.iloc[-1]["y"]),
            "event_count": event_count,
            "date_policy": date_policy_label(date_policy),
            "last_sync_at": (
                _format_sync_time(latest_sync.get("finished_at"))
                if latest_sync is not None
                else "-"
            ),
            "anomaly_count": anomaly_count,
            "anomaly_rate_pct": anomaly_count / row_count * 100,
            "mae": metrics["mae"],
            "rmse": metrics["rmse"],
            "mape": metrics["mape"],
            "coverage": metrics["coverage"],
            "saved_run_id": run_id,
            "sync_message": sync_result.message,
        },
        anomaly_points,
    )


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
                st.success(
                    f"{result.message}; fetched {result.fetched_rows} rows."
                )
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
            format_func=lambda event_id: _event_option_label(events, event_id),
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

    tabs = st.tabs(["Forecast", "Anomalies", "Backtest", "Events", "Data"])

    with tabs[0]:
        st.plotly_chart(
            make_forecast_chart(
                prophet_df,
                forecast,
                anomalies,
                events=db_events if active_holidays is not None else None,
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
                _prepare_anomaly_table(anomaly_points),
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
        render_data_tab(symbol, period, history, date_policy, storage_status)


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
        m1.metric("MAE", _format_metric(metrics["mae"]))
        m2.metric("RMSE", _format_metric(metrics["rmse"]))
        m3.metric("MAPE", _format_metric(metrics["mape"], "%"))
        m4.metric("Coverage", _format_metric(metrics["coverage"], "%"))
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
    state_key = _rolling_state_key(
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
        _format_horizon_label(best_row["horizon_days"]),
    )
    metric_cols[1].metric("Best MAPE", _format_metric(best_row["mape"], "%"))
    metric_cols[2].metric(
        "Avg coverage",
        _format_metric(rolling_summary["coverage"].mean(), "%"),
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

    db1, db2, db3, db4, db5 = st.columns(5)
    db1.metric("Stored price rows", f"{summary['daily_prices']:,}")
    db2.metric("Symbols", f"{summary['symbols']:,}")
    db3.metric("Sync runs", f"{summary['sync_runs']:,}")
    db4.metric("Events", f"{summary['events']:,}")
    db5.metric("Backtests", f"{summary['backtest_runs']:,}")

    cv1, cv2, cv3, cv4 = st.columns(4)
    cv1.metric("Selected rows", f"{coverage.row_count:,}")
    cv2.metric("Stored range", _format_date_range(coverage.start_date, coverage.end_date))
    cv3.metric("Freshness days", _format_optional_number(coverage.freshness_days))
    cv4.metric("Longest gap", f"{coverage.longest_missing_business_day_run:,} expected days")

    st.subheader("Recent sync runs")
    st.dataframe(storage_status["recent_sync_runs"], width="stretch", hide_index=True)

    st.subheader("Price history")
    st.dataframe(history, width="stretch", hide_index=True)


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
    state_key = _multi_state_key(
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
                ),
            }

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
    c2.metric("Best MAPE", f"{best_row['ticker']} · {_format_metric(best_row['mape'], '%')}")
    c3.metric(
        "Highest anomaly rate",
        f"{anomaly_row['ticker']} · {_format_metric(anomaly_row['anomaly_rate_pct'], '%')}",
    )
    c4.metric("Fetched rows", f"{int(summary['fetched_rows'].sum()):,}")
    st.caption(
        f"Data range: {summary['data_start_date'].min()} ~ {summary['latest_date'].max()} · "
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


st.title("Ticker Scope")

with st.sidebar:
    st.markdown("### Analysis")
    analysis_view = st.radio(
        "View",
        ["Single ticker", "Multi ticker"],
        horizontal=False,
    )

    if analysis_view == "Single ticker":
        selected_symbol = st.selectbox("Preset", DEFAULT_SYMBOLS, index=0)
        custom_symbol = st.text_input("Custom ticker", value="").strip().upper()
        symbol = custom_symbol or selected_symbol
        symbols = []
    else:
        selected_symbols = st.multiselect(
            "Preset tickers",
            DEFAULT_SYMBOLS,
            default=DEFAULT_SYMBOLS[:4],
        )
        custom_symbols_text = st.text_input(
            "Custom tickers",
            value="",
            placeholder="META, NFLX",
        )
        symbols = _normalize_symbol_list(selected_symbols, custom_symbols_text)
        symbol = ""

    st.divider()
    st.markdown("### Data")
    period = st.selectbox("Period", ["1y", "3y", "5y", "10y", "max"], index=2)
    date_policy = st.selectbox(
        "Date handling",
        DATE_POLICY_OPTIONS,
        index=0,
        format_func=date_policy_label,
        help=(
            "US stock trading days excludes weekends and NYSE holidays. "
            "Daily calendar days keeps every date for service metrics such as plays."
        ),
    )
    force_refresh = st.button("Sync now", width="stretch")

    st.divider()
    st.markdown("### Model")
    forecast_days = st.slider("Forecast days", min_value=7, max_value=180, value=30, step=7)
    interval_width = st.slider(
        "Interval width",
        min_value=0.5,
        max_value=0.95,
        value=0.8,
        step=0.05,
    )
    use_events = st.checkbox("Use DB events", value=True)
    run_backtest = (
        st.checkbox("Backtest", value=True)
        if analysis_view == "Single ticker"
        else False
    )

try:
    if force_refresh:
        cached_history.clear()

    if analysis_view == "Single ticker":
        render_single_ticker_view(
            symbol=symbol,
            period=period,
            forecast_days=forecast_days,
            interval_width=interval_width,
            use_events=use_events,
            date_policy=date_policy,
            run_backtest=run_backtest,
            force_refresh=force_refresh,
        )
    else:
        render_multi_ticker_view(
            symbols=symbols,
            period=period,
            forecast_days=forecast_days,
            interval_width=interval_width,
            use_events=use_events,
            date_policy=date_policy,
            force_refresh=force_refresh,
        )

except Exception as exc:
    st.error(str(exc))
