"""User resolution for bot and internal-API call sites.

In self-host mode, a single ``User`` row is auto-created at startup from
``ADMIN_CHAT_ID`` and cached in-process. In cloud mode (Phase 6+), the
resolver looks up by Telegram user id and returns ``None`` for unknown
users so that the onboarding handler can upsert them.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

if TYPE_CHECKING:
    from telegram import Update


# Module-level cache of the singleton user's UUID. Populated by ``init_bot``
# at startup. In cloud mode this remains ``None``.
_singleton_user_id: uuid.UUID | None = None


async def ensure_singleton_user(session: AsyncSession, telegram_user_id: int) -> User:
    """Return the ``User`` row for *telegram_user_id*, creating it if missing.

    Idempotent: safe to call repeatedly. Handles concurrent inserts via
    ``IntegrityError`` re-select (the ``telegram_user_id`` UNIQUE constraint
    on ``users`` makes a duplicate INSERT race-safe).

    The caller is responsible for committing the session.
    """
    # SQLAlchemy 2.0 select pattern (cf. app/services/projects.py:53-55).
    result = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(telegram_user_id=telegram_user_id)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        # Lost an INSERT race against another worker — roll back the failed
        # insert and re-select the row that the winner committed.
        await session.rollback()
        result = await session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        user = result.scalar_one()
    return user


async def get_current_user(session: AsyncSession, update: Update) -> User | None:
    """Resolve the ``User`` for the caller of a Telegram ``Update``.

    Self-host mode (Phase 3.1, current): returns the bootstrapped singleton
    user — keyed off the cached ``_singleton_user_id`` populated by
    ``init_bot``. Returns ``None`` if the singleton has not been bootstrapped
    yet (defensive; should not happen in production).

    Cloud mode: not implemented until Phase 6.
    """
    cloud_mode = False  # TODO(Phase 6): drive from ``settings.cloud_mode``.
    if cloud_mode:
        # TODO(Phase 6): cloud-mode branch — look up by
        # ``update.effective_user.id`` and return ``None`` for unknown users
        # so the onboarding handler can upsert them.
        raise NotImplementedError("Cloud-mode user resolution lands in Phase 6.")

    # Self-host branch.
    if _singleton_user_id is None:
        return None
    result = await session.execute(select(User).where(User.id == _singleton_user_id))
    return result.scalar_one_or_none()
