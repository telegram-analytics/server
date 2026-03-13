"""Phase 5 — Chart generation tests.

All tests are pure unit tests (no DB, no real QuickChart).
The httpx AsyncClient is patched to return controlled responses.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_FAKE_PNG = _PNG_MAGIC + b"\x00" * 100


def _make_mock_client(status: int = 200, content: bytes = _FAKE_PNG) -> MagicMock:
    """Return a mock httpx.AsyncClient whose .post() returns *content*."""
    mock_response = MagicMock()
    mock_response.status_code = status
    mock_response.content = content
    mock_response.text = content.decode("latin-1", errors="replace")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


_SAMPLE_DATA = [
    {"bucket": datetime(2024, 1, 1, tzinfo=UTC), "count": 10},
    {"bucket": datetime(2024, 1, 2, tzinfo=UTC), "count": 20},
    {"bucket": datetime(2024, 1, 3, tzinfo=UTC), "count": 5},
]


# ── generate_line_chart ───────────────────────────────────────────────────


async def test_generate_line_chart_returns_bytes():
    from app.services.charts import generate_line_chart

    mock_client = _make_mock_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await generate_line_chart(
            _SAMPLE_DATA,
            title="purchase",
            period_label="7d",
        )
    assert isinstance(result, bytes)
    assert len(result) > 0


async def test_generate_line_chart_returns_valid_png():
    from app.services.charts import generate_line_chart

    mock_client = _make_mock_client(content=_FAKE_PNG)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await generate_line_chart(
            _SAMPLE_DATA,
            title="signup",
            period_label="30d",
        )
    assert result[:4] == b"\x89PNG"


async def test_generate_line_chart_sends_title_in_payload():
    from app.services.charts import generate_line_chart

    mock_client = _make_mock_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        await generate_line_chart(_SAMPLE_DATA, title="my_event", period_label="7d")

    call_kwargs = mock_client.post.call_args
    payload = call_kwargs[1]["json"] if call_kwargs[1] else call_kwargs[0][1]
    chart = payload["chart"]
    title_text = chart["options"]["plugins"]["title"]["text"]
    assert "my_event" in title_text


async def test_generate_line_chart_empty_data_does_not_raise():
    from app.services.charts import generate_line_chart

    mock_client = _make_mock_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await generate_line_chart([], title="no_data", period_label="7d")
    assert isinstance(result, bytes)


# ── generate_comparison_chart ─────────────────────────────────────────────


async def test_generate_comparison_chart_returns_valid_png():
    from app.services.charts import generate_comparison_chart

    mock_client = _make_mock_client(content=_FAKE_PNG)
    data_b = [
        {"bucket": datetime(2024, 1, 1, tzinfo=UTC), "count": 3},
        {"bucket": datetime(2024, 1, 2, tzinfo=UTC), "count": 8},
    ]
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await generate_comparison_chart(
            _SAMPLE_DATA, data_b, label_a="this week", label_b="last week"
        )
    assert result[:4] == b"\x89PNG"


async def test_generate_comparison_chart_has_two_datasets():
    from app.services.charts import generate_comparison_chart

    mock_client = _make_mock_client()
    data_b = [{"bucket": datetime(2024, 1, 1, tzinfo=UTC), "count": 2}]
    with patch("httpx.AsyncClient", return_value=mock_client):
        await generate_comparison_chart(_SAMPLE_DATA, data_b, label_a="A", label_b="B")

    call_kwargs = mock_client.post.call_args
    payload = call_kwargs[1]["json"] if call_kwargs[1] else call_kwargs[0][1]
    datasets = payload["chart"]["data"]["datasets"]
    assert len(datasets) == 2
    labels = {d["label"] for d in datasets}
    assert labels == {"A", "B"}


# ── error handling ────────────────────────────────────────────────────────


async def test_quickchart_500_raises_chart_generation_error():
    from app.services.charts import ChartGenerationError, generate_line_chart

    mock_client = _make_mock_client(status=500, content=b"internal error")
    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(ChartGenerationError, match="HTTP 500"),
    ):
        await generate_line_chart(_SAMPLE_DATA, title="t", period_label="7d")


async def test_quickchart_network_error_raises_chart_generation_error():
    import httpx as _httpx

    from app.services.charts import ChartGenerationError, generate_line_chart

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=_httpx.ConnectError("refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(ChartGenerationError, match="unreachable"),
    ):
        await generate_line_chart(_SAMPLE_DATA, title="t", period_label="7d")
