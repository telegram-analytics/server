"""Security utilities: API key generation, hashing, and validation."""

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


def generate_api_key() -> str:
    """Return a new ``proj_<64 hex chars>`` API key.

    The raw key is only ever shown once (at project creation time).
    The caller is responsible for storing the hash, not the plaintext.
    """
    return "proj_" + secrets.token_hex(32)


def hash_api_key(api_key: str) -> str:
    """Return the SHA-256 hex digest of *api_key*."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def validate_api_key(api_key: str, session: AsyncSession) -> Project | None:
    """Return the Project whose api_key_hash matches *api_key*, or None.

    Used by ingestion endpoints to authenticate incoming events.
    """
    key_hash = hash_api_key(api_key)
    result = await session.execute(select(Project).where(Project.api_key_hash == key_hash))
    return result.scalar_one_or_none()
