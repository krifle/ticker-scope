from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

_CACHE_ROOT = Path(__file__).resolve().parents[2] / ".cache"
_MPL_CACHE_DIR = _CACHE_ROOT / "matplotlib"
_XDG_CACHE_DIR = _CACHE_ROOT / "xdg"
_MPL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_XDG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CACHE_DIR))
os.environ.setdefault("XDG_CACHE_HOME", str(_XDG_CACHE_DIR))

from prophet import Prophet

from ticker_scope.date_policy import CALENDAR_DAY, make_future_dataframe


def build_model(
    holidays: pd.DataFrame | None = None,
    interval_width: float = 0.8,
    weekly_seasonality: bool = True,
    yearly_seasonality: bool = True,
) -> Prophet:
    holidays_arg = None if holidays is None or holidays.empty else holidays
    return Prophet(
        holidays=holidays_arg,
        interval_width=interval_width,
        weekly_seasonality=weekly_seasonality,
        yearly_seasonality=yearly_seasonality,
        daily_seasonality=False,
    )


def fit_and_forecast(
    prophet_df: pd.DataFrame,
    periods: int,
    holidays: pd.DataFrame | None = None,
    interval_width: float = 0.8,
    date_policy: str = CALENDAR_DAY,
) -> tuple[Prophet, pd.DataFrame]:
    if prophet_df.empty:
        raise ValueError("Prophet input data is empty.")

    model = build_model(holidays=holidays, interval_width=interval_width)
    model.fit(prophet_df)
    future = make_future_dataframe(
        prophet_df,
        periods=periods,
        date_policy=date_policy,
        include_history=True,
    )
    forecast = model.predict(future)
    return model, forecast


def predict_dates(
    prophet_df: pd.DataFrame,
    dates: pd.Series,
    holidays: pd.DataFrame | None = None,
    interval_width: float = 0.8,
) -> pd.DataFrame:
    model = build_model(holidays=holidays, interval_width=interval_width)
    model.fit(prophet_df)
    future = pd.DataFrame({"ds": pd.to_datetime(dates)})
    return model.predict(future)
