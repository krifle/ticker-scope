from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd

from ticker_scope.data.repositories import classify_fear_greed_value
from ticker_scope.observability import get_logger


CNN_FEAR_GREED_SOURCE = "cnn_api"
LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class FearGreedRecord:
    index_date: date
    value: float
    classification: str | None = None
    raw_timestamp: int | None = None
    notes: str | None = None


class FearGreedClient(Protocol):
    def fetch_history(self, last: str = "365") -> pd.DataFrame:
        """Return normalized Fear & Greed records."""


class CnnFearGreedClient:
    def fetch_history(self, last: str = "365") -> pd.DataFrame:
        try:
            import fear_greed
        except ImportError as exc:
            raise RuntimeError(
                "The 'fear-greed' package is not installed. "
                "Install project requirements before syncing CNN Fear & Greed data."
            ) from exc

        LOGGER.info(
            "API request provider=cnn_fear_greed package=fear_greed.get_history last=%s",
            last,
        )
        try:
            raw_history = fear_greed.get_history(last=last)
        except TypeError:
            raw_history = fear_greed.get_history(last)

        history = normalize_cnn_fear_greed_history(raw_history)
        LOGGER.info(
            "API parsed provider=cnn_fear_greed rows=%s",
            len(history),
        )
        return history


def normalize_cnn_fear_greed_history(raw_history) -> pd.DataFrame:
    records = []
    for item in raw_history or []:
        record = _record_from_item(item)
        if record is not None:
            records.append(record)

    return pd.DataFrame(
        [
            {
                "index_date": record.index_date,
                "value": record.value,
                "classification": record.classification
                or classify_fear_greed_value(record.value),
                "raw_timestamp": record.raw_timestamp,
                "notes": record.notes,
            }
            for record in records
        ]
    )


def _record_from_item(item) -> FearGreedRecord | None:
    if isinstance(item, dict):
        raw_date = item.get("date") or item.get("index_date") or item.get("timestamp")
        raw_value = item.get("score") or item.get("value")
        classification = item.get("rating") or item.get("classification")
        raw_timestamp = item.get("timestamp")
    else:
        raw_date = getattr(item, "date", None) or getattr(item, "timestamp", None)
        raw_value = getattr(item, "score", None) or getattr(item, "value", None)
        classification = getattr(item, "rating", None) or getattr(
            item,
            "classification",
            None,
        )
        raw_timestamp = getattr(item, "timestamp", None)

    if raw_date is None or raw_value is None:
        return None

    index_date = _coerce_index_date(raw_date)
    value = float(raw_value)
    if index_date is None or value < 0 or value > 100:
        return None

    raw_timestamp = _optional_timestamp(raw_timestamp)
    return FearGreedRecord(
        index_date=index_date,
        value=value,
        classification=str(classification).title() if classification else None,
        raw_timestamp=raw_timestamp,
        notes="Provider: CNN Fear & Greed via fear-greed",
    )


def _coerce_index_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).date()

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text)).date()

    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _optional_timestamp(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return None
