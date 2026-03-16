"""Shared constants for bot handlers."""

from datetime import timedelta

PERIODS: dict[str, timedelta] = {
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}

PERIOD_LABEL: dict[str, str] = {
    "7d": "last 7 days",
    "30d": "last 30 days",
    "90d": "last 90 days",
}
