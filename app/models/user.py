"""SQLAlchemy ORM model for the users table.

A ``User`` represents the Telegram account that owns one or more projects.
In self-host mode there is typically a single user (backfilled from
``ADMIN_CHAT_ID`` at migration time). In cloud mode, a ``User`` row is
created the first time a new Telegram account interacts with the bot.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """A Telegram account that owns projects."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    telegram_user_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        unique=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )
