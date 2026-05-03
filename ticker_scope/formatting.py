from __future__ import annotations

import pandas as pd


def format_date_range(start_date, end_date) -> str:
    if start_date is None or end_date is None:
        return "-"
    return f"{start_date} ~ {end_date}"


def format_optional_number(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value:,}"


def format_optional_days(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value:,} days"


def format_sync_time(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "-"
    return timestamp.tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M KST")


def latest_sync_label(recent_sync_runs: pd.DataFrame) -> str:
    if recent_sync_runs.empty:
        return "-"
    row = recent_sync_runs.iloc[0]
    status = str(row.get("status", "-"))
    return f"{format_sync_time(row.get('finished_at'))} · {status}"


def format_metric(value: float, suffix: str = "") -> str:
    if pd.isna(value):
        return "-"
    return f"{value:,.2f}{suffix}"


def format_horizon_label(value) -> str:
    if pd.isna(value):
        return "Holdout"
    return f"{int(value)}d"
