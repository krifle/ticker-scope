from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from ticker_scope.modeling.prophet_model import fit_and_forecast


MIN_REPLAY_TRAIN_ROWS = 30


def run_forecast_replay(
    prophet_df: pd.DataFrame,
    cutoff_date: date | datetime | pd.Timestamp,
    periods: int,
    holidays: pd.DataFrame | None = None,
    interval_width: float = 0.8,
    date_policy: str = "calendar_day",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    normalized = prophet_df.sort_values("ds").reset_index(drop=True)
    cutoff = pd.Timestamp(cutoff_date).normalize()
    train_df = normalized[normalized["ds"] <= cutoff].reset_index(drop=True)
    if len(train_df) < MIN_REPLAY_TRAIN_ROWS:
        raise ValueError(
            f"At least {MIN_REPLAY_TRAIN_ROWS} rows are required before the cutoff."
        )

    _, forecast = fit_and_forecast(
        train_df,
        periods=periods,
        holidays=holidays,
        interval_width=interval_width,
        date_policy=date_policy,
    )
    return train_df, forecast
