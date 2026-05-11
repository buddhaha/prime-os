"""
Alembic environment — supports both sync (psycopg2) and async (asyncpg) URLs.

When called from main.py at startup, the URL is already rewritten to psycopg2
so this runs as a plain sync migration. When called from the CLI with an asyncpg
URL, it switches to async mode automatically.

Run from the repo root:
    DATABASE_URL=postgresql+psycopg2://prime:prime_dev@localhost/prime alembic upgrade head
    DATABASE_URL=postgresql+psycopg2://prime:prime_dev@localhost/prime alembic revision --autogenerate -m "..."
"""

import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context

# ── Import ORM metadata for autogenerate ──────────────────────────────────────
from backend.database import Base

alembic_cfg = context.config

if alembic_cfg.config_file_name is not None:
    fileConfig(alembic_cfg.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """
    Priority: sqlalchemy.url set by caller (main.py) > DATABASE_URL env > alembic.ini.
    Normalises asyncpg URLs to psycopg2 for sync Alembic runs.
    """
    url = alembic_cfg.get_main_option("sqlalchemy.url")
    if not url:
        url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("No DATABASE_URL — set the env var or sqlalchemy.url in alembic.ini")
    # Alembic runs sync; replace async driver if present
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


# ── Offline mode ──────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (sync psycopg2) ───────────────────────────────────────────────

def run_migrations_online() -> None:
    engine = create_engine(get_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


# ── Entry point ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
