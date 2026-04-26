"""Project CRUD service.

All functions accept an ``AsyncSession`` and flush but do NOT commit —
the caller (API layer) is responsible for committing or rolling back.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key, hash_api_key
from app.models.project import Project
from app.models.settings import ProjectSettings


async def create_project(
    session: AsyncSession,
    *,
    name: str,
    admin_chat_id: int,
    owner_user_id: uuid.UUID | None = None,
    domain_allowlist: list[str] | None = None,
) -> tuple[Project, str]:
    """Create a project and its default settings row.

    Returns ``(project, plaintext_api_key)``.  The plaintext key is the
    ONLY time it is exposed — it is NOT stored in the database.

    Both ``admin_chat_id`` and ``owner_user_id`` are written to the row.
    ``admin_chat_id`` remains required while the column is still NOT NULL
    in the schema; ``owner_user_id`` is the authoritative ownership link
    going forward and should be supplied by all new call sites. It is
    typed as optional only so legacy/transitional callers (e.g. the
    internal HTTP API in ``app/api/projects.py``) can land without
    breaking until Phase 3.4 wires them through ``ensure_singleton_user``.
    """
    api_key = generate_api_key()
    project = Project(
        name=name,
        api_key_hash=hash_api_key(api_key),
        admin_chat_id=admin_chat_id,
        owner_user_id=owner_user_id,
        domain_allowlist=domain_allowlist or [],
    )
    session.add(project)
    await session.flush()

    # Auto-create settings with defaults so every project always has a row.
    settings = ProjectSettings(project_id=project.id)
    session.add(settings)
    await session.flush()

    await session.refresh(project)
    return project, api_key


async def list_projects(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
) -> list[Project]:
    """Return all projects belonging to *owner_user_id*, ordered by creation."""
    result = await session.execute(
        select(Project).where(Project.owner_user_id == owner_user_id).order_by(Project.created_at)
    )
    return list(result.scalars().all())


async def get_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> Project | None:
    """Return a project by ID, or None if not found / not owned by user."""
    result = await session.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_user_id == owner_user_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> bool:
    """Delete a project (cascades to all child rows). Returns False if not found."""
    project = await get_project(session, project_id, owner_user_id)
    if project is None:
        return False
    await session.delete(project)
    await session.flush()
    return True
