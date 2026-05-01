from __future__ import annotations

import pandas as pd


EVENT_COLUMNS = ["holiday", "ds", "lower_window", "upper_window"]


def empty_events() -> pd.DataFrame:
    return pd.DataFrame(columns=EVENT_COLUMNS)


def make_event(
    name: str,
    date: str,
    lower_window: int = 0,
    upper_window: int = 0,
) -> pd.DataFrame:
    return normalize_events(
        pd.DataFrame(
            {
                "holiday": [name],
                "ds": [date],
                "lower_window": [lower_window],
                "upper_window": [upper_window],
            }
        )
    )


def normalize_events(events: pd.DataFrame | None) -> pd.DataFrame | None:
    if events is None or events.empty:
        return None

    normalized = events.copy()
    normalized["holiday"] = normalized["holiday"].astype(str).str.strip()
    normalized["ds"] = pd.to_datetime(normalized["ds"], errors="coerce")

    for column in ("lower_window", "upper_window"):
        if column not in normalized.columns:
            normalized[column] = 0
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0)
        normalized[column] = normalized[column].astype(int)

    normalized = normalized.dropna(subset=["holiday", "ds"])
    normalized = normalized[normalized["holiday"] != ""]
    return normalized[EVENT_COLUMNS].reset_index(drop=True)


def events_to_holidays(events: pd.DataFrame | None) -> pd.DataFrame | None:
    if events is None or events.empty:
        return None

    required = {"name", "event_date"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing required event columns: {sorted(missing)}")

    holidays = events.copy()
    holidays["holiday"] = holidays["name"]
    holidays["ds"] = holidays["event_date"]
    return normalize_events(holidays)
