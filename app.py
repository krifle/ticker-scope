from __future__ import annotations

import streamlit as st

from ticker_scope.data.market_data import symbol_label
from ticker_scope.ui.data_access import clear_cached_history
from ticker_scope.ui.sidebar import render_sidebar
from ticker_scope.ui.views.multi import render_multi_ticker_view
from ticker_scope.ui.views.single import render_single_ticker_view


def main() -> None:
    st.set_page_config(page_title="Ticker Scope", layout="wide")

    controls = render_sidebar()
    st.title("Ticker Scope")
    if controls.analysis_view == "Single ticker":
        st.header(symbol_label(controls.symbol))

    try:
        if controls.force_refresh:
            clear_cached_history()

        if controls.analysis_view == "Single ticker":
            render_single_ticker_view(
                symbol=controls.symbol,
                period=controls.period,
                forecast_days=controls.forecast_days,
                interval_width=controls.interval_width,
                use_events=controls.use_events,
                date_policy=controls.date_policy,
                run_backtest=controls.run_backtest,
                force_refresh=controls.force_refresh,
            )
        else:
            render_multi_ticker_view(
                symbols=controls.symbols,
                period=controls.period,
                forecast_days=controls.forecast_days,
                interval_width=controls.interval_width,
                use_events=controls.use_events,
                date_policy=controls.date_policy,
                force_refresh=controls.force_refresh,
            )

    except Exception as exc:
        st.error(str(exc))


if __name__ == "__main__":
    main()
