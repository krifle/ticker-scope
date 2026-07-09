from __future__ import annotations

from dataclasses import dataclass
from io import StringIO

import pandas as pd
import requests

from ticker_scope.config import get_alpha_vantage_api_key
from ticker_scope.observability import get_logger, masked_params


ALPHA_VANTAGE_EARNINGS_URL = "https://www.alphavantage.co/query"
ALPHA_VANTAGE_EARNINGS_SOURCE = "alpha_vantage_earnings"
ALPHA_VANTAGE_HORIZONS = ("3month", "6month", "12month")
LOGGER = get_logger(__name__)


class EventProviderError(RuntimeError):
    pass


class EventProviderRateLimitError(EventProviderError):
    pass


@dataclass(frozen=True)
class EarningsCalendarRequest:
    symbol: str
    horizon: str = "3month"
    api_key: str | None = None


class AlphaVantageEarningsClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        base_url: str = ALPHA_VANTAGE_EARNINGS_URL,
        timeout: int = 20,
    ) -> None:
        self.session = session or requests.Session()
        self.base_url = base_url
        self.timeout = timeout

    def fetch_earnings_calendar(
        self,
        request: EarningsCalendarRequest,
    ) -> pd.DataFrame:
        symbol = request.symbol.strip().upper()
        if not symbol:
            raise ValueError("Ticker symbol is required.")

        horizon = _normalize_horizon(request.horizon)
        api_key = get_alpha_vantage_api_key(request.api_key)
        if not api_key:
            raise EventProviderError(
                "ALPHA_VANTAGE_API_KEY is not configured. "
                "Set it in .env, environment variables, or the UI field."
            )

        params = {
            "function": "EARNINGS_CALENDAR",
            "symbol": symbol,
            "horizon": horizon,
            "apikey": api_key,
        }
        LOGGER.info(
            "API request provider=alpha_vantage url=%s params=%s",
            self.base_url,
            masked_params(params),
        )
        response = self.session.get(
            self.base_url,
            params=params,
            timeout=self.timeout,
        )
        LOGGER.info(
            "API response provider=alpha_vantage url=%s status_code=%s",
            self.base_url,
            response.status_code,
        )
        if response.status_code == 429:
            raise EventProviderRateLimitError("Alpha Vantage rate limit reached.")
        response.raise_for_status()

        events = normalize_alpha_vantage_earnings_csv(
            response.text,
            requested_symbol=symbol,
        )
        LOGGER.info(
            "API parsed provider=alpha_vantage ticker=%s rows=%s",
            symbol,
            len(events),
        )
        return events


def normalize_alpha_vantage_earnings_csv(
    csv_text: str,
    requested_symbol: str | None = None,
) -> pd.DataFrame:
    text = csv_text.strip()
    if not text:
        return _empty_earnings_frame()
    if _looks_like_limit_message(text):
        raise EventProviderRateLimitError(text[:240])

    calendar = pd.read_csv(StringIO(text))
    if calendar.empty:
        return _empty_earnings_frame()

    calendar.columns = [str(column).strip() for column in calendar.columns]
    required = {"symbol", "reportDate"}
    if not required.issubset(calendar.columns):
        raise EventProviderError(
            "Unexpected Alpha Vantage earnings calendar response. "
            f"Columns: {', '.join(calendar.columns)}"
        )

    result = pd.DataFrame()
    result["ticker"] = calendar["symbol"].astype(str).str.strip().str.upper()
    result["event_date"] = pd.to_datetime(
        calendar["reportDate"],
        errors="coerce",
    ).dt.date
    result["name"] = result["ticker"].apply(lambda value: f"{value} earnings")
    result["category"] = "earnings"
    result["lower_window"] = -1
    result["upper_window"] = 1
    result["source"] = ALPHA_VANTAGE_EARNINGS_SOURCE
    result["notes"] = calendar.apply(_alpha_vantage_notes, axis=1)
    result = result.dropna(subset=["event_date"])
    if requested_symbol is not None:
        result = result[result["ticker"] == requested_symbol.strip().upper()]
    return result.reset_index(drop=True)


def _alpha_vantage_notes(row: pd.Series) -> str:
    parts = ["Provider: Alpha Vantage"]
    for label, column in (
        ("Company", "name"),
        ("Fiscal period end", "fiscalDateEnding"),
        ("EPS estimate", "estimate"),
        ("Currency", "currency"),
    ):
        if column in row and pd.notna(row[column]) and str(row[column]).strip():
            parts.append(f"{label}: {row[column]}")
    return " | ".join(parts)


def _normalize_horizon(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALPHA_VANTAGE_HORIZONS:
        raise ValueError(
            "Unsupported Alpha Vantage horizon. "
            f"Use one of: {', '.join(ALPHA_VANTAGE_HORIZONS)}"
        )
    return normalized


def _looks_like_limit_message(text: str) -> bool:
    lowered = text.lower()
    return (
        "thank you for using alpha vantage" in lowered
        or "our standard api call frequency" in lowered
        or "rate limit" in lowered
        or lowered.startswith("{")
    )


def _empty_earnings_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ticker",
            "event_date",
            "name",
            "category",
            "lower_window",
            "upper_window",
            "source",
            "notes",
        ]
    )
