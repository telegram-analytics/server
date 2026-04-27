"""Privacy primitives: daily salt rotation, visitor hashing, PII scrubbing.

Phase 4.1 lands the daily-salt helper. Subsequent phases extend this module
with ``hash_visitor``, ``parse_user_agent``, ``scrub_properties`` and the
log-redaction filter.

The salt is the single source of randomness used to bind a visitor identity
to one UTC day. It rotates automatically because the cache key is keyed by
``YYYYMMDD``: yesterday's salt is unreachable from today's hash inputs.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from app.core.redis_client import get_redis

_SALT_KEY_PREFIX = "ip_salt:"
_SALT_TTL_SECONDS = 60 * 60 * 48  # 48h, covers UTC-day boundary slack
_SALT_BYTES = 32  # 64 hex chars
_ONE_DAY = timedelta(days=1)

# Self-host fallback cache, keyed by ``YYYYMMDD``. Populated lazily and
# trimmed to today + yesterday to bound memory.
_local_salt_cache: dict[str, str] = {}


def _today_key() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def _trim_local_cache(today: str) -> None:
    """Keep only today's and yesterday's entries in the local cache."""
    if len(_local_salt_cache) <= 2:
        return
    today_dt = datetime.strptime(today, "%Y%m%d")
    yesterday = (today_dt - _ONE_DAY).strftime("%Y%m%d")
    keep = {today, yesterday}
    for k in list(_local_salt_cache.keys()):
        if k not in keep:
            _local_salt_cache.pop(k, None)


async def get_today_salt() -> str:
    """Return the salt for the current UTC day, generating it if missing.

    Backed by Redis when configured (so all replicas hash identically); falls
    back to a process-local cache otherwise. The Redis path uses
    ``SET NX EX`` followed by a re-``GET`` so concurrent generators converge
    on a single value.
    """
    today = _today_key()
    key = f"{_SALT_KEY_PREFIX}{today}"
    client = get_redis()

    if client is None:
        # Self-host single-replica fallback.
        cached = _local_salt_cache.get(today)
        if cached is not None:
            return cached
        candidate = secrets.token_hex(_SALT_BYTES)
        # ``setdefault`` makes the in-memory path race-safe under
        # ``asyncio.gather``: only the first coroutine's value sticks.
        salt = _local_salt_cache.setdefault(today, candidate)
        _trim_local_cache(today)
        return salt

    existing = await client.get(key)
    if existing is not None:
        return existing

    candidate = secrets.token_hex(_SALT_BYTES)
    # Atomic insert-if-absent; we don't trust the bool return — we always
    # re-GET so racing callers converge on whichever value won.
    await client.set(key, candidate, ex=_SALT_TTL_SECONDS, nx=True)
    winner = await client.get(key)
    if winner is None:
        # Defensive: the key was evicted between SET and GET. Fall back to
        # our candidate; the next caller will re-populate.
        return candidate
    return winner
