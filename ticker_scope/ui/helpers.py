from __future__ import annotations

from datetime import date

import pandas as pd

from ticker_scope.date_policy import date_policy_label
from ticker_scope.data.market_data import symbol_label
from ticker_scope.formatting import format_horizon_label


def prepare_anomaly_table(anomaly_points: pd.DataFrame) -> pd.DataFrame:
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


def event_option_label(events: pd.DataFrame, event_id: int) -> str:
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
    grouped["horizon_label"] = grouped["horizon_days"].apply(format_horizon_label)
    grouped["ticker_label"] = grouped["ticker"].apply(symbol_label)
    grouped["horizon_sort"] = grouped["horizon_days"].fillna(0).astype(int)
    grouped["run_label"] = grouped.apply(_make_run_label, axis=1)
    return grouped.sort_values(["run_id", "horizon_sort"], ascending=[False, True])


def rolling_state_key(
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


def normalize_symbol_list(
    preset_symbols: list[str],
    custom_symbols_text: str,
) -> list[str]:
    custom_symbols = [
        item.strip().upper()
        for item in custom_symbols_text.replace("\n", ",").split(",")
        if item.strip()
    ]
    return list(dict.fromkeys([*preset_symbols, *custom_symbols]))


def multi_state_key(
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


def _make_run_label(row: pd.Series) -> str:
    created_at = str(row["run_created_at"])[:16].replace("T", " ")
    event_label = "events" if bool(row["use_events"]) else "no events"
    date_label = date_policy_label(str(row.get("date_policy", "")))
    return (
        f"#{int(row['run_id'])} {symbol_label(str(row['ticker']))} {row['strategy']} "
        f"{row['period']} {event_label} {date_label} {created_at}"
    )
