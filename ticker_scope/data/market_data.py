from __future__ import annotations

from datetime import date
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from ticker_scope.observability import get_logger


LOGGER = get_logger(__name__)

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
    "005930.KS",
    "000660.KS",
]

SYMBOL_ALIASES = {
    "034020.KS": "두산에너빌리티",
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
}


@dataclass(frozen=True)
class MarketDataRequest:
    symbol: str = "TSLA"
    period: str = "5y"
    interval: str = "1d"
    auto_adjust: bool = True
    start: date | str | None = None
    end: date | str | None = None


def symbol_alias(symbol: str) -> str | None:
    return SYMBOL_ALIASES.get(symbol.strip().upper())


def symbol_label(symbol: str) -> str:
    normalized_symbol = symbol.strip().upper()
    alias = symbol_alias(normalized_symbol)
    if alias is None:
        return normalized_symbol
    return f"{normalized_symbol} · {alias}"


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

    LOGGER.info(
        "API request provider=yfinance endpoint=download ticker=%s interval=%s "
        "period=%s start=%s end=%s auto_adjust=%s",
        symbol,
        request.interval,
        download_args.get("period"),
        download_args.get("start"),
        download_args.get("end"),
        request.auto_adjust,
    )
    history = yf.download(**download_args)
    LOGGER.info(
        "API response provider=yfinance ticker=%s rows=%s empty=%s",
        symbol,
        len(history),
        history.empty,
    )

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
