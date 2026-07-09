from __future__ import annotations

from datetime import date
from dataclasses import dataclass

import pandas as pd
import yfinance as yf


DEFAULT_SYMBOLS = [
    "TSLA",
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "NLR",
    "URA",
    "034020.KS",
]


@dataclass(frozen=True)
class MarketDataRequest:
    symbol: str = "TSLA"
    period: str = "5y"
    interval: str = "1d"
    auto_adjust: bool = True
    start: date | str | None = None
    end: date | str | None = None


def load_price_history(request: MarketDataRequest) -> pd.DataFrame:
    symbol = request.symbol.strip().upper()
    if not symbol:
        raise ValueError("Ticker symbol is required.")

    download_args = {
        "tickers": symbol,
        "interval": request.interval,
        "auto_adjust": request.auto_adjust,
        "progress": False,
        "group_by": "column",
    }
    if request.start is not None or request.end is not None:
        download_args["start"] = request.start
        download_args["end"] = request.end
    else:
        download_args["period"] = request.period

    history = yf.download(**download_args)

    if history.empty:
        raise ValueError(f"No price history returned for {symbol}.")

    history = _flatten_yfinance_columns(history, symbol)
    if "Close" not in history.columns:
        raise ValueError(f"Close column is missing for {symbol}.")

    history = history.rename_axis("Date").reset_index()
    history["Date"] = pd.to_datetime(history["Date"]).dt.tz_localize(None)
    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column in history.columns:
            history[column] = pd.to_numeric(history[column], errors="coerce")
    history = history.dropna(subset=["Date", "Close"]).sort_values("Date")
    history["Symbol"] = symbol
    return history.reset_index(drop=True)


def to_prophet_frame(history: pd.DataFrame) -> pd.DataFrame:
    required = {"Date", "Close"}
    missing = required - set(history.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    prophet_df = history[["Date", "Close"]].rename(
        columns={"Date": "ds", "Close": "y"}
    )
    prophet_df["ds"] = pd.to_datetime(prophet_df["ds"])
    prophet_df["y"] = pd.to_numeric(prophet_df["y"], errors="coerce")
    return prophet_df.dropna(subset=["ds", "y"]).reset_index(drop=True)


def _flatten_yfinance_columns(history: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if not isinstance(history.columns, pd.MultiIndex):
        return history.copy()

    if symbol in history.columns.get_level_values(0):
        return history[symbol].copy()

    if symbol in history.columns.get_level_values(1):
        return history.xs(symbol, axis=1, level=1).copy()

    flattened = history.copy()
    flattened.columns = flattened.columns.get_level_values(0)
    return flattened
