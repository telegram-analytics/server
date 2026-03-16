"""Chart generation service wrapping the QuickChart API.

Charts are rendered as PNG images by sending a Chart.js configuration
object to the QuickChart HTTP service.  All functions are async and
raise ``ChartGenerationError`` on any failure so callers can fall back
to a text-only message gracefully.
"""

import logging
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

QUICKCHART_TIMEOUT = 10.0  # seconds
_LINE_COLOR = "rgb(99, 102, 241)"  # indigo-500
_LINE_COLOR_2 = "rgb(245, 158, 11)"  # amber-500
_PNG_MAGIC = b"\x89PNG"


class ChartGenerationError(Exception):
    """Raised when QuickChart returns an error or is unreachable."""


def _fmt_date(dt: datetime) -> str:
    """Format a datetime as a short label, e.g. '1 Jan'."""
    return dt.strftime("%-d %b")


async def generate_line_chart(
    data: list[dict[str, Any]],
    *,
    title: str,
    period_label: str,
    quickchart_url: str = "http://quickchart:3400",
) -> bytes:
    """Generate a single-series line chart and return PNG bytes.

    *data* is a list of ``{"bucket": datetime, "count": int}`` dicts as
    returned by ``analytics.events_over_time()``.

    Raises ``ChartGenerationError`` if QuickChart is unavailable or
    returns a non-200 response.
    """
    labels = [_fmt_date(row["bucket"]) for row in data]
    values = [row["count"] for row in data]

    config: dict[str, Any] = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": title,
                    "data": values,
                    "borderColor": _LINE_COLOR,
                    "backgroundColor": "rgba(99,102,241,0.1)",
                    "fill": True,
                    "tension": 0.3,
                    "pointRadius": 3,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {"display": True, "text": f"{title} — {period_label}"},
                "legend": {"display": False},
            },
            "scales": {"y": {"beginAtZero": True}},
        },
    }
    return await _post_chart(config, quickchart_url)


async def generate_comparison_chart(
    data_a: list[dict[str, Any]],
    data_b: list[dict[str, Any]],
    *,
    label_a: str,
    label_b: str,
    quickchart_url: str = "http://quickchart:3400",
) -> bytes:
    """Generate a two-series comparison line chart and return PNG bytes.

    Each dataset is a list of ``{"bucket": datetime, "count": int}`` dicts.
    Labels are taken from the longer dataset.
    """
    primary = data_a if len(data_a) >= len(data_b) else data_b
    labels = [_fmt_date(row["bucket"]) for row in primary]

    config: dict[str, Any] = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": label_a,
                    "data": [r["count"] for r in data_a],
                    "borderColor": _LINE_COLOR,
                    "fill": False,
                    "tension": 0.3,
                    "pointRadius": 3,
                },
                {
                    "label": label_b,
                    "data": [r["count"] for r in data_b],
                    "borderColor": _LINE_COLOR_2,
                    "fill": False,
                    "tension": 0.3,
                    "pointRadius": 3,
                },
            ],
        },
        "options": {
            "plugins": {"legend": {"display": True}},
            "scales": {"y": {"beginAtZero": True}},
        },
    }
    return await _post_chart(config, quickchart_url)


async def _post_chart(config: dict[str, Any], quickchart_url: str) -> bytes:
    """POST *config* to QuickChart and return the PNG response body."""
    payload = {
        "chart": config,
        "backgroundColor": "white",
        "format": "png",
        "width": 600,
        "height": 300,
    }
    try:
        async with httpx.AsyncClient(timeout=QUICKCHART_TIMEOUT) as client:
            response = await client.post(f"{quickchart_url}/chart", json=payload)
        if response.status_code != 200:
            msg = f"QuickChart returned HTTP {response.status_code}: {response.text[:300]}"
            logger.error("Chart generation failed: %s", msg)
            raise ChartGenerationError(msg)
        return response.content
    except httpx.HTTPError as exc:
        logger.error("QuickChart unreachable at %s: %s", quickchart_url, exc)
        raise ChartGenerationError(f"QuickChart unreachable: {exc}") from exc
