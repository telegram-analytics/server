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
    domain_allowlist: list[str] | None = None,
) -> tuple[Project, str]:
    """Create a project and its default settings row.

    Returns ``(project, plaintext_api_key)``.  The plaintext key is the
    ONLY time it is exposed — it is NOT stored in the database.
    """
    api_key = generate_api_key()
    project = Project(
        name=name,
        api_key_hash=hash_api_key(api_key),
        admin_chat_id=admin_chat_id,
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
    admin_chat_id: int,
) -> list[Project]:
    """Return all projects belonging to *admin_chat_id*, ordered by creation."""
    result = await session.execute(
        select(Project).where(Project.admin_chat_id == admin_chat_id).order_by(Project.created_at)
    )
    return list(result.scalars().all())


async def get_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    admin_chat_id: int,
) -> Project | None:
    """Return a project by ID, or None if not found / not owned by admin."""
    result = await session.execute(
        select(Project).where(
            Project.id == project_id,
            Project.admin_chat_id == admin_chat_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    admin_chat_id: int,
) -> bool:
    """Delete a project (cascades to all child rows). Returns False if not found."""
    project = await get_project(session, project_id, admin_chat_id)
    if project is None:
        return False
    await session.delete(project)
    await session.flush()
    return True
