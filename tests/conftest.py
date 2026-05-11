"""
Shared fixtures for PRIME OS test suite.

Test isolation strategy:
  - A session-scoped engine creates/tears-down all tables once.
  - Each test function gets its own DB session wrapped in a transaction
    that is rolled back at the end — zero cleanup required per test.
  - The HTTP client overrides get_store / get_graph so it uses the same
    in-progress transaction, keeping API tests isolated too.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

from backend.database import Base
from backend.main import app
from backend.dependencies import get_store, get_graph
from backend.services.db_store import DBStore
from backend.services.graph_engine import GraphEngine

TEST_DB_URL = "postgresql+asyncpg://prime:prime_dev@db:5432/prime_test"


# ── One-time test database setup ──────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create prime_test DB if missing, then create all tables from ORM metadata."""
    # Use the prime DB with AUTOCOMMIT to issue CREATE DATABASE
    admin = create_async_engine(
        "postgresql+asyncpg://prime:prime_dev@db:5432/prime",
        isolation_level="AUTOCOMMIT",
    )
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = 'prime_test'")
        )
        if not exists:
            await conn.execute(text("CREATE DATABASE prime_test"))
    await admin.dispose()

    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Per-test isolated session ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session(test_engine):
    """
    Opens a real transaction at the start of each test and rolls it back
    at the end. Flushes within DBStore methods are visible inside the test
    but never hit the DB permanently.
    """
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        txn = await session.begin()
        try:
            yield session
        finally:
            await txn.rollback()


@pytest_asyncio.fixture
async def store(db_session):
    """DBStore backed by the test session."""
    return DBStore(db_session)


# ── HTTP test client ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_session):
    """
    AsyncClient pointing at the FastAPI app.
    - The app lifespan does NOT run (ASGITransport skips it).
    - get_store is overridden to use the test session.
    - get_graph is overridden with a fresh empty GraphEngine.
    """
    graph = GraphEngine()

    async def _store_override():
        # Must be an async generator to match FastAPI's Depends(get_store)
        yield DBStore(db_session)

    def _graph_override():
        return graph

    app.dependency_overrides[get_store] = _store_override
    app.dependency_overrides[get_graph] = _graph_override

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    app.dependency_overrides.clear()


# ── Convenience data factories ────────────────────────────────────────────────

def make_project_payload(**kwargs):
    base = dict(
        id="proj-test",
        name="Test Project",
        emoji="🧪",
        description="A project for testing",
        color="#00d4ff",
        status="active",
        project_type="personal",
        tags=[],
        progress="0",
    )
    base.update(kwargs)
    return base


def make_resource_payload(**kwargs):
    base = dict(
        type="article",
        title="Test Resource",
        description="Why this matters",
        source_url="https://example.com/test",
        project_ids=["proj-test"],
        tags=[],
        content="",
        status="inbox",
        origin="manual",
    )
    base.update(kwargs)
    return base


def make_proposal_payload(**kwargs):
    base = dict(
        project_id="proj-test",
        title="Deep dive into async Python",
        resource_type="article",
        source_url="https://example.com/async",
        read_time="15 min",
        why_relevant="Directly relevant to the async architecture decisions.",
        takeaways=["Use asyncio", "Avoid blocking calls", "Test with pytest-asyncio"],
        gap_type="concept",
        gap_label="async patterns",
    )
    base.update(kwargs)
    return base
