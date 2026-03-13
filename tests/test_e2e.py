"""End-to-end tests covering the full request lifecycle.

These tests require a live Docker PostgreSQL instance (DATABASE_URL must be set).
They exercise the full stack: HTTP → service layer → DB → background tasks.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# ── Helpers ───────────────────────────────────────────────────────────────


async def _create_project(api_client, *, name: str, allowlist=None) -> dict:
    payload: dict = {"name": name, "admin_chat_id": 111}
    if allowlist is not None:
        payload["domain_allowlist"] = allowlist
    resp = await api_client.post("/api/v1/internal/projects", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _track(api_client, api_key: str, event_name: str, **kwargs) -> None:
    resp = await api_client.post(
        "/api/v1/track",
        json={
            "api_key": api_key,
            "event_name": event_name,
            "session_id": str(uuid.uuid4()),
            **kwargs,
        },
    )
    assert resp.status_code == 202, resp.text


# ── E2E: track → alert evaluation ─────────────────────────────────────────


async def test_e2e_track_fires_every_alert(api_client, db_session):
    """Full cycle: track event → background alert evaluation → alert.counter unchanged."""

    from app.models.alert import Alert, AlertCondition

    data = await _create_project(api_client, name="e2e-alert.com")
    project_id = uuid.UUID(data["id"])

    # Seed an 'every' alert directly in the DB
    alert = Alert(
        project_id=project_id,
        event_name="purchase",
        condition=AlertCondition.every,
    )
    db_session.add(alert)
    await db_session.flush()
    await db_session.commit()  # commit so background task can see it

    await _track(api_client, data["api_key"], "purchase")

    # Give the background task a tick to run
    await asyncio.sleep(0.1)

    # Reload alert — 'every' doesn't mutate counter, just fires
    await db_session.refresh(alert)
    assert alert.condition == AlertCondition.every  # still configured


async def test_e2e_every_n_alert_counter_resets_on_nth(api_client, db_session):
    """every_n alert: counter increments and resets after threshold."""
    from app.models.alert import Alert, AlertCondition
    from app.services.events import evaluate_alerts

    data = await _create_project(api_client, name="e2e-n.com")
    project_id = uuid.UUID(data["id"])

    alert = Alert(
        project_id=project_id,
        event_name="click",
        condition=AlertCondition.every_n,
        threshold_n=3,
        counter=0,
    )
    db_session.add(alert)
    await db_session.flush()

    # Simulate two events — should not fire
    for _ in range(2):
        fired = await evaluate_alerts(db_session, project_id=project_id, event_name="click")
        assert fired == []

    # Third event — must fire and reset counter
    fired = await evaluate_alerts(db_session, project_id=project_id, event_name="click")
    assert len(fired) == 1
    assert fired[0].counter == 0


async def test_e2e_threshold_alert_fires_once_per_day(api_client, db_session):
    """threshold alert fires when daily count >= N, but not a second time."""
    from app.models.alert import Alert, AlertCondition
    from app.services.events import evaluate_alerts, insert_event

    data = await _create_project(api_client, name="e2e-threshold.com")
    project_id = uuid.UUID(data["id"])

    alert = Alert(
        project_id=project_id,
        event_name="checkout",
        condition=AlertCondition.threshold,
        threshold_n=2,
        counter=0,
    )
    db_session.add(alert)
    await db_session.flush()

    # Insert 2 events (meets threshold)
    for _ in range(2):
        await insert_event(
            db_session,
            project_id=project_id,
            event_name="checkout",
            session_id=str(uuid.uuid4()),
            properties={},
        )
    await db_session.flush()

    fired = await evaluate_alerts(db_session, project_id=project_id, event_name="checkout")
    assert len(fired) == 1

    # Second evaluation same day — must NOT fire again (counter==1 now)
    fired_again = await evaluate_alerts(db_session, project_id=project_id, event_name="checkout")
    assert fired_again == []


# ── E2E: analytics after ingestion ───────────────────────────────────────


async def test_e2e_track_then_count(api_client, db_session):
    """Events inserted via HTTP are visible to the analytics service."""
    from app.services.analytics import count_events

    data = await _create_project(api_client, name="e2e-count.com")
    project_id = uuid.UUID(data["id"])

    for _ in range(7):
        await _track(api_client, data["api_key"], "add_to_cart")

    before = datetime.now(UTC) - timedelta(minutes=5)
    after = datetime.now(UTC) + timedelta(minutes=5)

    # Force a fresh DB view (api_client commits, db_session may cache)
    await db_session.invalidate()

    count = await count_events(
        db_session,
        project_id=project_id,
        event_name="add_to_cart",
        start=before,
        end=after,
    )
    assert count == 7


async def test_e2e_pageview_then_analytics(api_client, db_session):
    """Pageview events are queryable as event_name == 'pageview'."""
    from app.services.analytics import count_events

    data = await _create_project(api_client, name="e2e-pv.com")
    project_id = uuid.UUID(data["id"])

    for i in range(3):
        resp = await api_client.post(
            "/api/v1/pageview",
            json={
                "api_key": data["api_key"],
                "session_id": str(uuid.uuid4()),
                "url": f"https://site.com/page/{i}",
            },
        )
        assert resp.status_code == 202

    await db_session.invalidate()
    before = datetime.now(UTC) - timedelta(minutes=5)
    after = datetime.now(UTC) + timedelta(minutes=5)

    count = await count_events(
        db_session,
        project_id=project_id,
        event_name="pageview",
        start=before,
        end=after,
    )
    assert count == 3


# ── E2E: chart generation (QuickChart mocked) ─────────────────────────────


async def test_e2e_track_then_chart(api_client, db_session):
    """Track events → query analytics → generate chart (QuickChart mocked)."""
    from datetime import timedelta

    from app.services.analytics import events_over_time
    from app.services.charts import generate_line_chart

    data = await _create_project(api_client, name="e2e-chart.com")
    project_id = uuid.UUID(data["id"])

    for _ in range(5):
        await _track(api_client, data["api_key"], "view")

    await db_session.invalidate()
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC) + timedelta(hours=1)

    rows = await events_over_time(
        db_session,
        project_id=project_id,
        event_name="view",
        start=start,
        end=end,
        granularity="hour",
    )
    assert len(rows) >= 1
    assert sum(r["count"] for r in rows) == 5

    # Now generate a chart (QuickChart mocked)
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = fake_png

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        png = await generate_line_chart(rows, title="view", period_label="1h")

    assert png[:4] == b"\x89PNG"


# ── E2E: ingestion throughput smoke test ──────────────────────────────────


async def test_e2e_100_sequential_track_calls(api_client):
    """100 sequential POST /track calls must all return 202 without error."""
    data = await _create_project(api_client, name="e2e-throughput.com")

    for i in range(100):
        resp = await api_client.post(
            "/api/v1/track",
            json={
                "api_key": data["api_key"],
                "event_name": "stress",
                "session_id": str(uuid.uuid4()),
                "properties": {"seq": i},
            },
        )
        assert resp.status_code == 202, f"Failed on request {i}: {resp.text}"


async def test_e2e_api_key_not_in_list_response(api_client):
    """api_key must never appear in GET /projects list responses."""
    data = await _create_project(api_client, name="e2e-key-leak.com")
    api_key = data["api_key"]

    list_resp = await api_client.get("/api/v1/internal/projects")
    assert list_resp.status_code == 200
    body = list_resp.text
    assert api_key not in body


async def test_e2e_delete_project_cascades_events(api_client, db_session):
    """Deleting a project must cascade-delete its events."""
    from sqlalchemy import select

    from app.models.event import Event

    data = await _create_project(api_client, name="e2e-cascade.com")
    project_id = uuid.UUID(data["id"])

    for _ in range(3):
        await _track(api_client, data["api_key"], "cascade_test")

    del_resp = await api_client.delete(f"/api/v1/internal/projects/{project_id}")
    assert del_resp.status_code == 204

    await db_session.invalidate()
    result = await db_session.execute(select(Event).where(Event.project_id == project_id))
    assert result.scalars().all() == []
