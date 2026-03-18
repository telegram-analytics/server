"""Event insertion and alert evaluation service."""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert, AlertCondition
from app.models.event import Event


async def insert_event(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    event_name: str,
    session_id: str,
    properties: dict,
    timestamp: datetime | None = None,
    url: str | None = None,
    referrer: str | None = None,
) -> Event:
    """Insert an event row.

    ``received_at`` is always server time (set by the DB default).
    ``timestamp`` defaults to server now() when the caller passes None.
    """
    event = Event(
        project_id=project_id,
        event_name=event_name,
        session_id=session_id,
        properties=properties,
        url=url,
        referrer=referrer,
    )
    if timestamp is not None:
        event.timestamp = timestamp
    session.add(event)
    await session.flush()
    await session.refresh(event)
    return event


async def evaluate_alerts(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    event_name: str,
) -> list[Alert]:
    """Evaluate all active alerts for *project_id* + *event_name*.

    Mutates alert counters in-place and flushes; the caller must commit.
    Returns the list of alerts that fired (for logging / notification).
    Does NOT send Telegram notifications — that is Phase 8's job.
    """
    now = datetime.now(UTC)
    result = await session.execute(
        select(Alert).where(
            Alert.project_id == project_id,
            Alert.event_name == event_name,
            Alert.is_active.is_(True),
            sa.or_(Alert.muted_until.is_(None), Alert.muted_until <= now),
        )
    )
    alerts = list(result.scalars().all())
    fired: list[Alert] = []

    for alert in alerts:
        if alert.condition == AlertCondition.every:
            fired.append(alert)

        elif alert.condition == AlertCondition.every_n:
            alert.counter += 1
            if alert.threshold_n and alert.counter >= alert.threshold_n:
                alert.counter = 0
                fired.append(alert)

        elif alert.condition == AlertCondition.threshold:
            today_start = datetime.combine(now.date(), datetime.min.time()).replace(tzinfo=UTC)
            count_result = await session.execute(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.project_id == project_id,
                    Event.event_name == event_name,
                    Event.received_at >= today_start,
                )
            )
            today_count = count_result.scalar_one()
            # counter == 0 means the alert has not yet fired today
            if alert.threshold_n and today_count >= alert.threshold_n and alert.counter == 0:
                alert.counter = 1
                fired.append(alert)

    await session.flush()
    return fired


def is_origin_allowed(domain_allowlist: list[str], origin: str | None) -> bool:
    """Return True if the request origin passes the allowlist check.

    * Empty allowlist → accept all origins (no restriction).
    * Non-empty allowlist + no Origin header → reject.
    * Non-empty allowlist → extract host and check membership.
    """
    if not domain_allowlist:
        return True
    if origin is None:
        return False
    from urllib.parse import urlparse

    host = urlparse(origin).netloc or origin
    normalized = {urlparse(d).netloc or d for d in domain_allowlist}
    return host in normalized
