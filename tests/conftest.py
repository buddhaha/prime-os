"""
Shared fixtures for PRIME OS test suite.

Isolation strategy: truncate all tables before each test (via the
autouse `isolate` fixture). This avoids asyncpg's "another operation
in progress" error that occurs when wrapping tests in manual rollback
transactions. Each test starts with a clean database.

Session-scoped engine: tables are created once per pytest run.
Function-scoped session: each test gets its own AsyncSession; SQLAlchemy
uses autobegin so flush() works without an explicit begin() call.
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
from backend.models.project import ProjectCreate, DecisionCreate, ConceptCreate
from backend.models.resource import ResourceCreate, ResourceType, ProposalCreate

TEST_DB_URL = "postgresql+asyncpg://prime:prime_dev@db:5432/prime_test"

_TABLES = [
    "proposals", "resource_projects", "resources",
    "concepts", "todos", "decisions", "projects",
]


# ── Session-scoped engine — tables are created once ──────────────────────────

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create prime_test database if missing, then build all ORM tables."""
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
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


# ── Per-test isolation via TRUNCATE (autouse) ─────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def isolate(test_engine):
    """Truncate all tables before every test for a clean slate."""
    async with test_engine.connect() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
        )
        await conn.commit()


# ── Per-test session ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session(test_engine):
    """
    Fresh AsyncSession per test. SQLAlchemy uses autobegin, so flush()
    works without an explicit begin() call. The session auto-rollbacks
    any uncommitted work when closed.
    """
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def store(db_session):
    return DBStore(db_session)


# ── HTTP client with dependency injection override ────────────────────────────

@pytest_asyncio.fixture
async def client(db_session):
    """
    AsyncClient pointing at the FastAPI app with the lifespan skipped.
    All requests share db_session so writes in one request are visible
    to subsequent queries in the same test (autobegin keeps them in one txn).
    """
    graph = GraphEngine()

    async def _store_override():
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


# ── Typed data factories ──────────────────────────────────────────────────────

def project_create(**kwargs) -> ProjectCreate:
    defaults = dict(name="Test Project", emoji="🧪", description="", color="#00d4ff")
    defaults.update(kwargs)
    return ProjectCreate(**defaults)


def resource_create(project_id: str, **kwargs) -> ResourceCreate:
    defaults = dict(
        type=ResourceType.article,
        title="Test Resource",
        description="Why this matters",
        source_url="https://example.com/test",
        project_ids=[project_id],
    )
    defaults.update(kwargs)
    return ResourceCreate(**defaults)


def proposal_create(project_id: str, **kwargs) -> ProposalCreate:
    defaults = dict(
        project_id=project_id,
        title="Deep dive into async Python",
        resource_type="article",
        source_url="https://example.com/async",
        read_time="15 min",
        why_relevant="Directly relevant to the async architecture decisions.",
        takeaways=["Use asyncio", "Avoid blocking calls", "Test with pytest-asyncio"],
        gap_type="concept",
        gap_label="async patterns",
    )
    defaults.update(kwargs)
    return ProposalCreate(**defaults)
