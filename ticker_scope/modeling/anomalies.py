from __future__ import annotations

import numpy as np
import pandas as pd


FORECAST_COLUMNS = ["ds", "yhat", "yhat_lower", "yhat_upper"]


def detect_interval_anomalies(
    actual: pd.DataFrame,
    forecast: pd.DataFrame,
) -> pd.DataFrame:
    merged = actual.merge(forecast[FORECAST_COLUMNS], on="ds", how="inner")
    merged["error"] = merged["y"] - merged["yhat"]
    merged["abs_error"] = merged["error"].abs()
    merged["interval_width_value"] = merged["yhat_upper"] - merged["yhat_lower"]
    merged["error_pct"] = np.where(
        merged["y"] != 0,
        merged["abs_error"] / merged["y"].abs() * 100,
        np.nan,
    )
    merged["is_anomaly"] = (merged["y"] < merged["yhat_lower"]) | (
        merged["y"] > merged["yhat_upper"]
    )
    merged["direction"] = np.select(
        [merged["y"] < merged["yhat_lower"], merged["y"] > merged["yhat_upper"]],
        ["below", "above"],
        default="inside",
    )
    merged["bound_exceeded"] = np.select(
        [merged["direction"] == "below", merged["direction"] == "above"],
        ["lower", "upper"],
        default="",
    )
    merged["distance_from_bound"] = np.select(
        [merged["direction"] == "below", merged["direction"] == "above"],
        [merged["yhat_lower"] - merged["y"], merged["y"] - merged["yhat_upper"]],
        default=0.0,
    )
    merged["distance_from_bound_pct"] = np.where(
        merged["y"] != 0,
        merged["distance_from_bound"] / merged["y"].abs() * 100,
        np.nan,
    )
    merged["interval_position"] = np.where(
        merged["interval_width_value"] != 0,
        (merged["y"] - merged["yhat_lower"]) / merged["interval_width_value"],
        np.nan,
    )
    merged["expected_range"] = merged.apply(
        lambda row: f"{row['yhat_lower']:,.2f} ~ {row['yhat_upper']:,.2f}",
        axis=1,
    )
    merged["explanation"] = merged.apply(_explain_anomaly_row, axis=1)
    return merged.sort_values("ds").reset_index(drop=True)


def anomaly_summary(anomalies: pd.DataFrame) -> pd.DataFrame:
    return (
        anomalies[anomalies["is_anomaly"]]
        .sort_values("error_pct", ascending=False)
        .reset_index(drop=True)
    )


def _explain_anomaly_row(row: pd.Series) -> str:
    if not bool(row["is_anomaly"]):
        return "Actual value stayed inside the forecast interval."

    direction = "above" if row["direction"] == "above" else "below"
    bound = "upper" if direction == "above" else "lower"
    distance = row["distance_from_bound"]
    distance_pct = row["distance_from_bound_pct"]
    return (
        f"Actual value is {direction} the {bound} forecast bound by "
        f"{distance:,.2f} ({distance_pct:,.2f}%)."
    )
