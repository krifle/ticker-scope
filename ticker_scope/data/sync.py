from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from ticker_scope.date_policy import AUTO_BY_TICKER, resolve_date_policy_for_symbol
from ticker_scope.data.database import get_connection, init_database
from ticker_scope.data.market_data import MarketDataRequest, load_price_history
from ticker_scope.data.repositories import (
    find_missing_price_ranges,
    get_daily_prices,
    get_first_price_date,
    get_last_price_date,
    record_sync_run,
    upsert_daily_prices,
)
from ticker_scope.observability import get_logger


LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class SyncResult:
    history: pd.DataFrame
    fetched_rows: int
    stored_rows: int
    from_cache: bool
    message: str


def sync_price_history(
    symbol: str,
    period: str = "5y",
    interval: str = "1d",
    auto_adjust: bool = True,
    force_refresh: bool = False,
    date_policy: str = AUTO_BY_TICKER,
) -> SyncResult:
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("Ticker symbol is required.")
    effective_date_policy = resolve_date_policy_for_symbol(symbol, date_policy)

    LOGGER.info(
        "Sync start source=yfinance ticker=%s period=%s interval=%s "
        "force_refresh=%s date_policy=%s",
        symbol,
        period,
        interval,
        force_refresh,
        effective_date_policy,
    )
    init_database()
    requested_start = period_to_start_date(period)
    today = date.today()
    started_at = _utc_now()
    fetched_rows = 0
    stored_rows = 0
    message = "cache hit"

    with get_connection() as connection:
        first_stored = get_first_price_date(
            connection,
            symbol,
            interval=interval,
            adjusted=auto_adjust,
        )
        last_stored = get_last_price_date(
            connection,
            symbol,
            interval=interval,
            adjusted=auto_adjust,
        )
        LOGGER.info(
            "DB read table=daily_prices ticker=%s first_stored=%s last_stored=%s "
            "interval=%s adjusted=%s",
            symbol,
            first_stored,
            last_stored,
            interval,
            auto_adjust,
        )
        missing_ranges = []
        if first_stored is not None and last_stored is not None:
            gap_start = first_stored
            if requested_start is not None:
                gap_start = max(first_stored, requested_start)
            if gap_start <= last_stored:
                missing_ranges = find_missing_price_ranges(
                    connection,
                    symbol,
                    start_date=gap_start,
                    end_date=last_stored,
                    interval=interval,
                    adjusted=auto_adjust,
                    min_business_day_run=5,
                    date_policy=effective_date_policy,
                )
                LOGGER.info(
                    "DB read table=daily_prices ticker=%s missing_ranges=%s",
                    symbol,
                    len(missing_ranges),
                )

        try:
            fetch_requests = _build_fetch_requests(
                symbol=symbol,
                period=period,
                interval=interval,
                auto_adjust=auto_adjust,
                requested_start=requested_start,
                first_stored=first_stored,
                last_stored=last_stored,
                today=today,
                force_refresh=force_refresh,
                missing_ranges=missing_ranges,
            )

            sync_messages = []
            LOGGER.info(
                "Sync fetch plan source=yfinance ticker=%s request_count=%s",
                symbol,
                len(fetch_requests),
            )
            for fetch_request in fetch_requests:
                LOGGER.info(
                    "Sync fetch source=yfinance ticker=%s period=%s start=%s end=%s",
                    symbol,
                    fetch_request.period,
                    fetch_request.start,
                    fetch_request.end,
                )
                downloaded = load_price_history(fetch_request)
                fetched_rows += len(downloaded)
                request_stored_rows = upsert_daily_prices(
                    connection,
                    symbol,
                    downloaded,
                    interval=interval,
                    adjusted=auto_adjust,
                )
                stored_rows += request_stored_rows
                LOGGER.info(
                    "DB write table=daily_prices ticker=%s rows=%s interval=%s "
                    "adjusted=%s",
                    symbol,
                    request_stored_rows,
                    interval,
                    auto_adjust,
                )
                sync_messages.append(_sync_message(fetch_request, request_stored_rows))

            if sync_messages:
                message = "; ".join(sync_messages)

            history = get_daily_prices(
                connection,
                symbol,
                start_date=requested_start,
                interval=interval,
                adjusted=auto_adjust,
            )
            LOGGER.info(
                "DB read table=daily_prices ticker=%s rows=%s start_date=%s "
                "interval=%s adjusted=%s",
                symbol,
                len(history),
                requested_start,
                interval,
                auto_adjust,
            )
            if history.empty:
                raise ValueError(f"No stored price history available for {symbol}.")

            record_sync_run(
                connection,
                source="yfinance",
                ticker=symbol,
                period=period,
                interval=interval,
                status="success",
                row_count=stored_rows,
                started_at=started_at,
                message=message,
            )
            LOGGER.info(
                "DB write table=sync_runs source=yfinance ticker=%s status=success "
                "row_count=%s message=%s",
                symbol,
                stored_rows,
                message,
            )
            connection.commit()

        except Exception as exc:
            LOGGER.exception("Sync failed source=yfinance ticker=%s", symbol)
            record_sync_run(
                connection,
                source="yfinance",
                ticker=symbol,
                period=period,
                interval=interval,
                status="failed",
                row_count=stored_rows,
                started_at=started_at,
                message=str(exc),
            )
            LOGGER.info(
                "DB write table=sync_runs source=yfinance ticker=%s status=failed "
                "row_count=%s message=%s",
                symbol,
                stored_rows,
                str(exc),
            )
            connection.commit()
            raise

    return SyncResult(
        history=history,
        fetched_rows=fetched_rows,
        stored_rows=stored_rows,
        from_cache=fetched_rows == 0,
        message=message,
    )


def period_to_start_date(period: str) -> date | None:
    period = period.lower().strip()
    today = date.today()
    if period == "max":
        return None
    if period.endswith("y"):
        return _subtract_years(today, int(period[:-1]))
    if period.endswith("mo"):
        return today - timedelta(days=30 * int(period[:-2]))
    if period.endswith("d"):
        return today - timedelta(days=int(period[:-1]))
    raise ValueError(f"Unsupported period: {period}")


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _build_fetch_requests(
    symbol: str,
    period: str,
    interval: str,
    auto_adjust: bool,
    requested_start: date | None,
    first_stored: date | None,
    last_stored: date | None,
    today: date,
    force_refresh: bool,
    missing_ranges: list[tuple[date, date, int]],
) -> list[MarketDataRequest]:
    if force_refresh or first_stored is None or last_stored is None:
        return [
            MarketDataRequest(
                symbol=symbol,
                period=period,
                interval=interval,
                auto_adjust=auto_adjust,
                start=requested_start,
                end=today + timedelta(days=1) if requested_start is not None else None,
            )
        ]

    requests: list[MarketDataRequest] = []

    needs_older_data = (
        requested_start is not None
        and first_stored > requested_start
        and (first_stored - requested_start).days > 7
    )
    if needs_older_data:
        requests.append(
            MarketDataRequest(
                symbol=symbol,
                period=period,
                interval=interval,
                auto_adjust=auto_adjust,
                start=requested_start,
                end=first_stored + timedelta(days=1),
            )
        )

    for gap_start, gap_end, _ in missing_ranges:
        requests.append(
            MarketDataRequest(
                symbol=symbol,
                period=period,
                interval=interval,
                auto_adjust=auto_adjust,
                start=gap_start,
                end=gap_end + timedelta(days=1),
            )
        )

    if (today - last_stored).days > 3:
        # Include the last stored date so late price corrections can overwrite it.
        requests.append(
            MarketDataRequest(
                symbol=symbol,
                period=period,
                interval=interval,
                auto_adjust=auto_adjust,
                start=last_stored,
                end=today + timedelta(days=1),
            )
        )

    return _merge_fetch_requests(
        requests,
        symbol=symbol,
        period=period,
        interval=interval,
        auto_adjust=auto_adjust,
    )


def _merge_fetch_requests(
    requests: list[MarketDataRequest],
    symbol: str,
    period: str,
    interval: str,
    auto_adjust: bool,
) -> list[MarketDataRequest]:
    if not requests:
        return []

    if any(request.start is None or request.end is None for request in requests):
        return requests

    ordered = sorted(requests, key=lambda request: _coerce_date(request.start))
    merged: list[tuple[date, date]] = []
    for request in ordered:
        request_start = _coerce_date(request.start)
        request_end = _coerce_date(request.end)
        if not merged:
            merged.append((request_start, request_end))
            continue

        current_start, current_end = merged[-1]
        if request_start <= current_end:
            merged[-1] = (current_start, max(current_end, request_end))
        else:
            merged.append((request_start, request_end))

    return [
        MarketDataRequest(
            symbol=symbol,
            period=period,
            interval=interval,
            auto_adjust=auto_adjust,
            start=start,
            end=end,
        )
        for start, end in merged
    ]


def _coerce_date(value: date | str | None) -> date:
    if isinstance(value, date):
        return value
    if value is None:
        raise ValueError("Date is required for range merging.")
    return date.fromisoformat(str(value)[:10])


def _sync_message(request: MarketDataRequest, stored_rows: int) -> str:
    if request.start is not None or request.end is not None:
        return f"synced {stored_rows} rows from {request.start} to {request.end}"
    return f"synced {stored_rows} rows for period {request.period}"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
