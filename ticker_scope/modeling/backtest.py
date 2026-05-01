from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ticker_scope.modeling.prophet_model import predict_dates


def split_train_test(
    prophet_df: pd.DataFrame,
    train_ratio: float = 0.8,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio must be between 0 and 1.")
    if len(prophet_df) < 30:
        raise ValueError("At least 30 rows are required for backtesting.")

    split_index = max(1, min(len(prophet_df) - 1, int(len(prophet_df) * train_ratio)))
    return (
        prophet_df.iloc[:split_index].reset_index(drop=True),
        prophet_df.iloc[split_index:].reset_index(drop=True),
    )


def run_holdout_backtest(
    prophet_df: pd.DataFrame,
    train_ratio: float = 0.8,
    holidays: pd.DataFrame | None = None,
    interval_width: float = 0.8,
) -> tuple[pd.DataFrame, dict[str, float]]:
    train_df, test_df = split_train_test(prophet_df, train_ratio=train_ratio)
    forecast = predict_dates(
        train_df,
        test_df["ds"],
        holidays=holidays,
        interval_width=interval_width,
    )

    result = test_df.merge(
        forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]],
        on="ds",
        how="inner",
    )
    metrics = score_forecast(result)
    return result, metrics


def make_holdout_metrics_frame(
    prophet_df: pd.DataFrame,
    metrics: dict[str, float],
    train_ratio: float = 0.8,
) -> pd.DataFrame:
    train_df, test_df = split_train_test(prophet_df, train_ratio=train_ratio)
    return pd.DataFrame(
        [
            {
                "horizon_days": None,
                "cutoff_date": train_df.iloc[-1]["ds"],
                "train_start_date": train_df.iloc[0]["ds"],
                "train_end_date": train_df.iloc[-1]["ds"],
                "test_start_date": test_df.iloc[0]["ds"],
                "test_end_date": test_df.iloc[-1]["ds"],
                "test_rows": len(test_df),
                **metrics,
            }
        ]
    )


def run_rolling_backtest(
    prophet_df: pd.DataFrame,
    horizons_days: list[int] | tuple[int, ...] = (7, 30, 90),
    rolling_windows: int = 4,
    min_train_rows: int = 252,
    holidays: pd.DataFrame | None = None,
    interval_width: float = 0.8,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(prophet_df) < 30:
        raise ValueError("At least 30 rows are required for backtesting.")

    normalized = prophet_df.sort_values("ds").reset_index(drop=True)
    horizons = _normalize_horizons(horizons_days)
    cutoffs = _select_rolling_cutoffs(
        normalized,
        horizons_days=horizons,
        rolling_windows=rolling_windows,
        min_train_rows=min_train_rows,
    )
    max_horizon = max(horizons)
    prediction_frames = []
    metric_rows = []

    for cutoff in cutoffs:
        train_df = normalized[normalized["ds"] <= cutoff].reset_index(drop=True)
        horizon_end = cutoff + pd.Timedelta(days=max_horizon)
        test_df = normalized[
            (normalized["ds"] > cutoff) & (normalized["ds"] <= horizon_end)
        ].reset_index(drop=True)

        if test_df.empty:
            continue

        forecast = predict_dates(
            train_df,
            test_df["ds"],
            holidays=holidays,
            interval_width=interval_width,
        )
        result = test_df.merge(
            forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]],
            on="ds",
            how="inner",
        )
        result["cutoff_date"] = cutoff
        result["train_start_date"] = train_df.iloc[0]["ds"]
        result["train_end_date"] = train_df.iloc[-1]["ds"]
        result["error"] = result["y"] - result["yhat"]
        result["abs_error"] = result["error"].abs()
        result["error_pct"] = result["abs_error"] / result["y"].abs() * 100

        for horizon in horizons:
            current_end = cutoff + pd.Timedelta(days=horizon)
            horizon_result = result[result["ds"] <= current_end].copy()
            if horizon_result.empty:
                continue

            horizon_result["horizon_days"] = horizon
            prediction_frames.append(horizon_result)
            scores = score_forecast(horizon_result)
            metric_rows.append(
                {
                    "horizon_days": horizon,
                    "cutoff_date": cutoff,
                    "train_start_date": train_df.iloc[0]["ds"],
                    "train_end_date": train_df.iloc[-1]["ds"],
                    "test_start_date": horizon_result.iloc[0]["ds"],
                    "test_end_date": horizon_result.iloc[-1]["ds"],
                    "test_rows": len(horizon_result),
                    **scores,
                }
            )

    predictions = (
        pd.concat(prediction_frames, ignore_index=True)
        if prediction_frames
        else pd.DataFrame()
    )
    metrics = pd.DataFrame(metric_rows)
    return predictions, metrics


def summarize_rolling_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return metrics.copy()

    return (
        metrics.groupby("horizon_days", dropna=False)
        .agg(
            windows=("cutoff_date", "nunique"),
            test_rows=("test_rows", "sum"),
            mae=("mae", "mean"),
            rmse=("rmse", "mean"),
            mape=("mape", "mean"),
            coverage=("coverage", "mean"),
            first_cutoff=("cutoff_date", "min"),
            last_cutoff=("cutoff_date", "max"),
        )
        .reset_index()
        .sort_values("horizon_days")
    )


def score_forecast(result: pd.DataFrame) -> dict[str, float]:
    error = result["y"] - result["yhat"]
    abs_error = error.abs()
    non_zero = result["y"] != 0

    mae = float(abs_error.mean())
    rmse = float(math.sqrt(np.square(error).mean()))
    mape = float((abs_error[non_zero] / result.loc[non_zero, "y"].abs()).mean() * 100)
    coverage = float(
        (
            (result["y"] >= result["yhat_lower"])
            & (result["y"] <= result["yhat_upper"])
        ).mean()
        * 100
    )

    return {
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "coverage": coverage,
    }


def _normalize_horizons(horizons_days: list[int] | tuple[int, ...]) -> list[int]:
    horizons = sorted({int(horizon) for horizon in horizons_days if int(horizon) > 0})
    if not horizons:
        raise ValueError("At least one positive horizon is required.")
    return horizons


def _select_rolling_cutoffs(
    prophet_df: pd.DataFrame,
    horizons_days: list[int],
    rolling_windows: int,
    min_train_rows: int,
) -> list[pd.Timestamp]:
    if rolling_windows < 1:
        raise ValueError("rolling_windows must be at least 1.")
    if min_train_rows < 30:
        raise ValueError("min_train_rows must be at least 30.")
    if len(prophet_df) <= min_train_rows:
        raise ValueError("Not enough rows after the minimum training window.")

    max_horizon = max(horizons_days)
    latest_cutoff = prophet_df.iloc[-1]["ds"] - pd.Timedelta(days=max_horizon)
    candidates = prophet_df[
        (prophet_df.index >= min_train_rows - 1)
        & (prophet_df["ds"] <= latest_cutoff)
    ]
    if candidates.empty:
        raise ValueError(
            "Not enough history to evaluate the selected horizons. "
            "Reduce horizon days or minimum train rows."
        )

    window_count = min(int(rolling_windows), len(candidates))
    positions = np.linspace(0, len(candidates) - 1, num=window_count, dtype=int)
    return list(dict.fromkeys(candidates.iloc[positions]["ds"].tolist()))
