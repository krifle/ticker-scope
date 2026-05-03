from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from ticker_scope.date_policy import date_policy_label
from ticker_scope.data.market_data import to_prophet_frame
from ticker_scope.data.sync import SyncResult, sync_price_history
from ticker_scope.events.calendar import events_to_holidays
from ticker_scope.formatting import format_sync_time
from ticker_scope.modeling.anomalies import anomaly_summary, detect_interval_anomalies
from ticker_scope.modeling.backtest import (
    make_holdout_metrics_frame,
    run_holdout_backtest,
)
from ticker_scope.modeling.prophet_model import fit_and_forecast
from ticker_scope.services.storage import (
    load_latest_sync_run,
    load_model_events,
    save_backtest_result,
)


HistoryLoader = Callable[[str, str, bool], SyncResult]
ProgressCallback = Callable[[int, int], None]
StatusCallback = Callable[[str, int, int], None]


def load_synced_history(symbol: str, period: str, force_refresh: bool) -> SyncResult:
    return sync_price_history(
        symbol=symbol,
        period=period,
        interval="1d",
        auto_adjust=True,
        force_refresh=force_refresh,
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
    history_loader: HistoryLoader | None = None,
    progress_callback: ProgressCallback | None = None,
    status_callback: StatusCallback | None = None,
) -> dict[str, pd.DataFrame]:
    summary_rows = []
    anomaly_frames = []
    error_rows = []
    total_symbols = len(symbols)
    load_history = history_loader or load_synced_history

    for index, symbol in enumerate(symbols, start=1):
        if status_callback is not None:
            status_callback(symbol, index, total_symbols)

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
                history_loader=load_history,
            )
            summary_rows.append(row)
            if not anomalies.empty:
                anomaly_frames.append(anomalies)
        except Exception as exc:
            error_rows.append({"ticker": symbol, "error": str(exc)})
        finally:
            if progress_callback is not None:
                progress_callback(index, total_symbols)

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
    history_loader: HistoryLoader | None = None,
) -> tuple[dict[str, object], pd.DataFrame]:
    load_history = history_loader or load_synced_history
    sync_result = load_history(symbol, period, force_refresh)
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
                format_sync_time(latest_sync.get("finished_at"))
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
