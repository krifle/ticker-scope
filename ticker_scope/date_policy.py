from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from typing import Iterable

import holidays
import pandas as pd


CALENDAR_DAY = "calendar_day"
US_STOCK_MARKET = "us_stock_market"

DATE_POLICY_OPTIONS = (US_STOCK_MARKET, CALENDAR_DAY)

DATE_POLICY_LABELS = {
    US_STOCK_MARKET: "US stock trading days",
    CALENDAR_DAY: "Daily calendar days",
}


def date_policy_label(value: str) -> str:
    return DATE_POLICY_LABELS.get(value, value)


def normalize_date_policy(value: str | None) -> str:
    if value is None:
        return CALENDAR_DAY

    normalized = value.strip().lower()
    aliases = {
        "d": CALENDAR_DAY,
        "day": CALENDAR_DAY,
        "daily": CALENDAR_DAY,
        "calendar": CALENDAR_DAY,
        "calendar_day": CALENDAR_DAY,
        "calendar_days": CALENDAR_DAY,
        "stock": US_STOCK_MARKET,
        "market": US_STOCK_MARKET,
        "trading": US_STOCK_MARKET,
        "business": US_STOCK_MARKET,
        "us_stock": US_STOCK_MARKET,
        "us_stock_market": US_STOCK_MARKET,
        "us_market": US_STOCK_MARKET,
        "nyse": US_STOCK_MARKET,
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError(f"Unsupported date policy: {value}")


def make_future_dataframe(
    prophet_df: pd.DataFrame,
    periods: int,
    date_policy: str = CALENDAR_DAY,
    include_history: bool = True,
) -> pd.DataFrame:
    if "ds" not in prophet_df.columns:
        raise ValueError("Prophet input must include a ds column.")
    if periods < 0:
        raise ValueError("periods must be greater than or equal to 0.")

    history_dates = _normalize_datetime_series(prophet_df["ds"])
    if history_dates.empty:
        raise ValueError("Prophet input data is empty.")

    future_dates = make_future_dates(
        last_date=history_dates.max(),
        periods=periods,
        date_policy=date_policy,
    )
    frames = []
    if include_history:
        frames.append(history_dates)
    if not future_dates.empty:
        frames.append(future_dates)

    if not frames:
        return pd.DataFrame({"ds": pd.Series(dtype="datetime64[ns]")})

    dates = pd.concat(frames, ignore_index=True).drop_duplicates().sort_values()
    return pd.DataFrame({"ds": dates.reset_index(drop=True)})


def make_future_dates(
    last_date: date | datetime | pd.Timestamp,
    periods: int,
    date_policy: str = CALENDAR_DAY,
) -> pd.Series:
    if periods < 0:
        raise ValueError("periods must be greater than or equal to 0.")
    if periods == 0:
        return pd.Series(dtype="datetime64[ns]")

    policy = normalize_date_policy(date_policy)
    last_timestamp = _normalize_timestamp(last_date)
    if policy == CALENDAR_DAY:
        return pd.Series(
            pd.date_range(
                start=last_timestamp + pd.Timedelta(days=1),
                periods=periods,
                freq="D",
            )
        )

    dates: list[pd.Timestamp] = []
    current = last_timestamp
    while len(dates) < periods:
        current += pd.Timedelta(days=1)
        if is_us_stock_trading_day(current):
            dates.append(current)
    return pd.Series(dates, dtype="datetime64[ns]")


def expected_dates_between(
    start_date: date | datetime | pd.Timestamp,
    end_date: date | datetime | pd.Timestamp,
    date_policy: str = US_STOCK_MARKET,
) -> list[date]:
    start_timestamp = _normalize_timestamp(start_date)
    end_timestamp = _normalize_timestamp(end_date)
    if start_timestamp > end_timestamp:
        return []

    policy = normalize_date_policy(date_policy)
    dates = pd.date_range(start=start_timestamp, end=end_timestamp, freq="D")
    if policy == CALENDAR_DAY:
        return [item.date() for item in dates]

    return [item.date() for item in dates if is_us_stock_trading_day(item)]


def next_expected_date(
    value: date | datetime | pd.Timestamp,
    date_policy: str = US_STOCK_MARKET,
) -> date:
    policy = normalize_date_policy(date_policy)
    current = _normalize_timestamp(value)
    while True:
        current += pd.Timedelta(days=1)
        if policy == CALENDAR_DAY or is_us_stock_trading_day(current):
            return current.date()


def is_us_stock_trading_day(value: date | datetime | pd.Timestamp) -> bool:
    normalized = _normalize_timestamp(value).date()
    if normalized.weekday() >= 5:
        return False
    return normalized not in _nyse_holiday_dates((normalized.year,))


@lru_cache(maxsize=16)
def _nyse_holiday_dates(years: tuple[int, ...]) -> set[date]:
    return set(holidays.financial_holidays("NYSE", years=years).keys())


def _normalize_datetime_series(values: Iterable[object]) -> pd.Series:
    series = pd.Series(pd.to_datetime(values, errors="coerce"))
    series = series.dropna()
    if getattr(series.dt, "tz", None) is None:
        series = series.dt.tz_localize(None)
    else:
        series = series.dt.tz_convert(None)
    series = series.dt.normalize()
    return series.drop_duplicates().sort_values().reset_index(drop=True)


def _normalize_timestamp(value: date | datetime | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is not None:
        timestamp = timestamp.tz_convert(None)
    return timestamp.normalize()
