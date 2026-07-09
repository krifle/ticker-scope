from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ticker_scope.date_policy import DATE_POLICY_OPTIONS, date_policy_label
from ticker_scope.data.market_data import DEFAULT_SYMBOLS, symbol_label
from ticker_scope.ui.helpers import normalize_symbol_list


@dataclass(frozen=True)
class AppControls:
    analysis_view: str
    symbol: str
    symbols: list[str]
    period: str
    date_policy: str
    force_refresh: bool
    forecast_days: int
    interval_width: float
    use_events: bool
    run_backtest: bool


def render_sidebar() -> AppControls:
    with st.sidebar:
        st.markdown("### Analysis")
        analysis_view = st.radio(
            "View",
            ["Single ticker", "Multi ticker"],
            horizontal=False,
        )

        if analysis_view == "Single ticker":
            selected_symbol = st.selectbox(
                "Preset",
                DEFAULT_SYMBOLS,
                index=0,
                format_func=symbol_label,
            )
            custom_symbol = st.text_input("Custom ticker", value="").strip().upper()
            symbol = custom_symbol or selected_symbol
            symbols = []
        else:
            selected_symbols = st.multiselect(
                "Preset tickers",
                DEFAULT_SYMBOLS,
                default=DEFAULT_SYMBOLS[:4],
                format_func=symbol_label,
            )
            custom_symbols_text = st.text_input(
                "Custom tickers",
                value="",
                placeholder="META, NFLX, 034020.KS",
            )
            symbols = normalize_symbol_list(selected_symbols, custom_symbols_text)
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
                "Auto by ticker uses Korea trading days for .KS/.KQ symbols and "
                "US trading days for other tickers. Daily calendar days keeps every date."
            ),
        )
        force_refresh = st.button("Sync now", width="stretch")

        st.divider()
        st.markdown("### Model")
        forecast_days = st.slider(
            "Forecast days",
            min_value=7,
            max_value=180,
            value=30,
            step=7,
        )
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

    return AppControls(
        analysis_view=analysis_view,
        symbol=symbol,
        symbols=symbols,
        period=period,
        date_policy=date_policy,
        force_refresh=force_refresh,
        forecast_days=forecast_days,
        interval_width=interval_width,
        use_events=use_events,
        run_backtest=run_backtest,
    )
