from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ticker_scope.modeling.forecast_replay import (
    MIN_REPLAY_TRAIN_ROWS,
    run_forecast_replay,
)
from ticker_scope.ui.charts import make_forecast_replay_chart


def render_forecast_replay_tab(
    symbol: str,
    period: str,
    prophet_df: pd.DataFrame,
    forecast_days: int,
    active_holidays: pd.DataFrame | None,
    interval_width: float,
    use_events: bool,
    date_policy: str,
) -> None:
    if len(prophet_df) < MIN_REPLAY_TRAIN_ROWS:
        st.info(
            f"Forecast Replay needs at least {MIN_REPLAY_TRAIN_ROWS} price rows."
        )
        return

    normalized = prophet_df.sort_values("ds").reset_index(drop=True)
    available_dates = [item.date() for item in normalized["ds"]]
    state_key = _cutoff_state_key(
        symbol=symbol,
        period=period,
        forecast_days=forecast_days,
        interval_width=interval_width,
        use_events=use_events,
        date_policy=date_policy,
    )
    cutoff_date = _resolve_cutoff_date(
        st.session_state.get(state_key),
        available_dates,
    )
    cutoff_index = available_dates.index(cutoff_date)

    previous_col, slider_col, next_col = st.columns([0.12, 0.76, 0.12])
    with previous_col:
        previous_clicked = st.button(
            "←",
            disabled=cutoff_index <= MIN_REPLAY_TRAIN_ROWS - 1,
            help="Move to the previous available price date.",
            width="stretch",
        )
    with next_col:
        next_clicked = st.button(
            "→",
            disabled=cutoff_index >= len(available_dates) - 1,
            help="Move to the next available price date.",
            width="stretch",
        )

    if previous_clicked:
        cutoff_index = max(MIN_REPLAY_TRAIN_ROWS - 1, cutoff_index - 1)
    if next_clicked:
        cutoff_index = min(len(available_dates) - 1, cutoff_index + 1)
    cutoff_date = available_dates[cutoff_index]

    with slider_col:
        selected_date = st.select_slider(
            "Cutoff date",
            options=available_dates[MIN_REPLAY_TRAIN_ROWS - 1 :],
            value=cutoff_date,
            help=(
                "Drag to jump across available price dates, then use the arrows "
                "for one-day fine tuning."
            ),
        )
    cutoff_date = selected_date
    st.session_state[state_key] = cutoff_date.isoformat()

    train_df, replay_forecast = _cached_forecast_replay(
        normalized,
        cutoff_date,
        forecast_days,
        active_holidays,
        interval_width,
        date_policy,
    )

    st.caption(
        f"Training through {cutoff_date.isoformat()} · "
        f"{len(train_df):,} rows used · Forecast {forecast_days:,} days"
    )
    st.plotly_chart(
        make_forecast_replay_chart(
            normalized,
            replay_forecast,
            pd.Timestamp(cutoff_date),
        ),
        width="stretch",
    )


@st.cache_data(ttl=900, show_spinner="Replaying forecast...")
def _cached_forecast_replay(
    prophet_df: pd.DataFrame,
    cutoff_date: date,
    forecast_days: int,
    holidays: pd.DataFrame | None,
    interval_width: float,
    date_policy: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return run_forecast_replay(
        prophet_df,
        cutoff_date=cutoff_date,
        periods=forecast_days,
        holidays=holidays,
        interval_width=interval_width,
        date_policy=date_policy,
    )


def _resolve_cutoff_date(value: object, available_dates: list[date]) -> date:
    if value is not None:
        candidate = pd.Timestamp(value).date()
        if candidate in available_dates:
            return candidate
        earlier_dates = [item for item in available_dates if item <= candidate]
        if earlier_dates:
            return earlier_dates[-1]
    return available_dates[-1]


def _cutoff_state_key(
    symbol: str,
    period: str,
    forecast_days: int,
    interval_width: float,
    use_events: bool,
    date_policy: str,
) -> str:
    return (
        "forecast_replay_cutoff:"
        f"{symbol}:{period}:{forecast_days}:{interval_width}:"
        f"{use_events}:{date_policy}"
    )
