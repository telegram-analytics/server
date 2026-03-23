"""Pydantic schemas for event ingestion requests and responses."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Reject timestamps more than 1 day in the future or more than 1 year in the past.
_MAX_FUTURE = timedelta(days=1)
_MAX_PAST = timedelta(days=365)

# Cap number of entries in properties dict to prevent resource exhaustion.
_MAX_PROPERTIES = 100


def _validate_timestamp(v: datetime | None) -> datetime | None:
    if v is None:
        return v
    now = datetime.now(UTC)
    # Ensure timezone-aware comparison
    ts = v if v.tzinfo is not None else v.replace(tzinfo=UTC)
    if ts > now + _MAX_FUTURE:
        raise ValueError("timestamp is too far in the future")
    if ts < now - _MAX_PAST:
        raise ValueError("timestamp is too far in the past")
    return v


def _validate_properties(v: dict[str, Any]) -> dict[str, Any]:
    if len(v) > _MAX_PROPERTIES:
        raise ValueError(f"properties must have at most {_MAX_PROPERTIES} entries")
    return v


class TrackEventRequest(BaseModel):
    api_key: str = Field(..., min_length=1, max_length=255)
    event_name: str = Field(..., min_length=1, max_length=255)
    session_id: str = Field(..., min_length=1, max_length=512)
    properties: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None

    _validate_timestamp = field_validator("timestamp")(_validate_timestamp)
    _validate_properties = field_validator("properties")(_validate_properties)


class PageviewRequest(BaseModel):
    api_key: str = Field(..., min_length=1, max_length=255)
    session_id: str = Field(..., min_length=1, max_length=512)
    url: str = Field(..., min_length=1, max_length=2048)
    referrer: str | None = Field(default=None, max_length=2048)
    timestamp: datetime | None = None
    properties: dict[str, Any] = Field(default_factory=dict)

    _validate_timestamp = field_validator("timestamp")(_validate_timestamp)
    _validate_properties = field_validator("properties")(_validate_properties)


class EventResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    event_name: str
    properties: dict[str, Any]
    session_id: str
    url: str | None
    referrer: str | None
    timestamp: datetime
    received_at: datetime

    model_config = {"from_attributes": True}
