"""Privacy primitives: daily salt rotation, visitor hashing, PII scrubbing.

Phase 4.1 lands the daily-salt helper. Subsequent phases extend this module
with ``hash_visitor``, ``parse_user_agent``, ``scrub_properties`` and the
log-redaction filter.

The salt is the single source of randomness used to bind a visitor identity
to one UTC day. It rotates automatically because the cache key is keyed by
``YYYYMMDD``: yesterday's salt is unreachable from today's hash inputs.
"""

from __future__ import annotations

import functools
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from ua_parser import user_agent_parser

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


# ── Visitor hashing ────────────────────────────────────────────────────────

_VISITOR_HASH_LEN = 16  # 64-bit truncation; collision odds acceptable per project/day


async def hash_visitor(project_id: uuid.UUID, client_ip: str, user_agent: str) -> str:
    """Return a stable, daily-rotating visitor identifier.

    Formula (pinned — do not change without a coordinated migration):

        salt = await get_today_salt()
        raw  = f"{salt}{project_id}{client_ip}{user_agent}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    Properties:
    * Idempotent for (project, IP, UA) within one UTC day.
    * Rotates at UTC midnight because ``get_today_salt`` is keyed by date.
    * Bound to ``project_id`` so the same visitor on two different projects
      yields different hashes (no cross-project correlation).
    * Truncated to 16 hex chars (64 bits) — fits the ``events.visitor_hash``
      ``String(16)`` column. Widening would require a migration.
    """
    salt = await get_today_salt()
    raw = f"{salt}{project_id}{client_ip}{user_agent}".encode()
    return hashlib.sha256(raw).hexdigest()[:_VISITOR_HASH_LEN]


# ── User-Agent parsing ─────────────────────────────────────────────────────

_UNKNOWN = "Unknown"
_BOT_DEVICE_FAMILIES = {"Spider"}


def _classify_device_type(device_family: str, os_family: str) -> str:
    """Map ua-parser device + os heuristics to a coarse device-type bucket.

    Returns one of: ``"mobile" | "tablet" | "desktop" | "bot" | "unknown"``.
    """
    if device_family in _BOT_DEVICE_FAMILIES:
        return "bot"
    df = device_family.lower() if device_family else ""
    of = os_family.lower() if os_family else ""

    if "ipad" in df or "tablet" in df or of == "android" and "tablet" in df:
        return "tablet"
    if df == "ipad":
        return "tablet"

    # Mobile OSes signal phones unless the device family says tablet (handled above).
    if of in {"ios", "android", "windows phone", "blackberry os", "kaios"}:
        return "mobile"
    if "iphone" in df or "mobile" in df or "phone" in df:
        return "mobile"

    if df in {"other", ""} and of in {"other", ""}:
        return "unknown"

    # Desktop OSes (Windows, Mac OS X, Linux, ChromeOS, etc.) and "Other"
    # device family with a known OS → desktop.
    return "desktop"


@functools.lru_cache(maxsize=1024)
def parse_user_agent(ua: str) -> tuple[str, str, str]:
    """Parse a User-Agent string into ``(browser, os, device_type)``.

    * ``browser`` — UA family (e.g. ``"Chrome"``, ``"Firefox"``); ``"Unknown"``
      when missing or reported as ``"Other"``.
    * ``os`` — OS family (e.g. ``"Mac OS X"``, ``"iOS"``); ``"Unknown"`` when
      missing or reported as ``"Other"``.
    * ``device_type`` — one of ``"mobile" | "tablet" | "desktop" | "bot" |
      "unknown"`` derived from the parsed device + os families.

    Cached for the last 1024 distinct UA strings via ``functools.lru_cache``
    — UA distributions are heavily skewed, so this dramatically cuts repeated
    parse cost on the hot ingestion path.
    """
    if not ua:
        return (_UNKNOWN, _UNKNOWN, "unknown")

    parsed = user_agent_parser.Parse(ua)
    ua_part = parsed.get("user_agent") or {}
    os_part = parsed.get("os") or {}
    device_part = parsed.get("device") or {}

    browser_family = (ua_part.get("family") or "").strip()
    os_family = (os_part.get("family") or "").strip()
    device_family = (device_part.get("family") or "").strip()

    browser = browser_family if browser_family and browser_family != "Other" else _UNKNOWN
    os_name = os_family if os_family and os_family != "Other" else _UNKNOWN
    device_type = _classify_device_type(device_family, os_family)

    return (browser, os_name, device_type)
