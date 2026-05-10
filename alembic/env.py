"""
Alembic environment — async SQLAlchemy (asyncpg).

Run from the repo root:
    alembic revision --autogenerate -m "description"
    alembic upgrade head
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Import our ORM metadata for autogenerate ──
from backend.database import Base

# Alembic Config object
alembic_cfg = context.config

# Wire up Python logging from alembic.ini
if alembic_cfg.config_file_name is not None:
    fileConfig(alembic_cfg.config_file_name)

# Metadata for autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """Read DATABASE_URL from env (set by Docker / .env), falling back to alembic.ini."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    url = alembic_cfg.get_main_option("sqlalchemy.url")
    if url:
        return url
    raise RuntimeError("DATABASE_URL not set. Export it or add sqlalchemy.url to alembic.ini.")


# ── Offline mode (generates SQL without connecting) ──────────────────────────

def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (connects via asyncpg) ───────────────────────────────────────

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = async_engine_from_config(
        {"sqlalchemy.url": get_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ── Entry point ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
