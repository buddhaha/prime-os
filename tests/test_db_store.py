"""
Integration tests for DBStore — all run against the test Postgres DB
and are rolled back automatically after each test.
"""

import json
import pytest
from datetime import date

from backend.services.db_store import DBStore
from backend.models.project import ProjectCreate, DecisionCreate, TodoCreate, ConceptCreate
from backend.models.resource import (
    ResourceCreate, ResourceUpdate, ResourceType, ResourceStatus, ResourceOrigin,
    ProposalCreate,
)
from tests.conftest import make_proposal_payload


# ── Projects ──────────────────────────────────────────────────────────────────

async def test_create_and_list_project(store: DBStore):
    proj = await store.create_project(ProjectCreate(
        id="test-proj", name="Test Project", emoji="🧪",
        description="desc", color="#fff", status="active",
        project_type="personal", tags=[], progress="0",
    ))
    assert proj.id == "test-proj"
    assert proj.name == "Test Project"

    projects = await store.list_projects()
    assert any(p.id == "test-proj" for p in projects)


async def test_get_project(store: DBStore):
    await store.create_project(ProjectCreate(
        id="proj-get", name="Get Me", emoji="📁", description="",
        color="#000", status="active", project_type="work", tags=[], progress="0",
    ))
    detail = await store.get_project("proj-get")
    assert detail is not None
    assert detail.project.name == "Get Me"


async def test_get_project_not_found(store: DBStore):
    result = await store.get_project("nonexistent")
    assert result is None


# ── Resources ─────────────────────────────────────────────────────────────────

async def _seed_project(store: DBStore, id="proj-1"):
    return await store.create_project(ProjectCreate(
        id=id, name="Seed Project", emoji="📁", description="",
        color="#000", status="active", project_type="personal", tags=[], progress="0",
    ))


async def test_create_resource(store: DBStore):
    await _seed_project(store)
    r = await store.create_resource(ResourceCreate(
        type=ResourceType.article,
        title="Test Article",
        description="Why this matters",
        source_url="https://example.com",
        project_ids=["proj-1"],
        tags=["python"],
        content="",
    ))
    assert r.title == "Test Article"
    assert r.status == ResourceStatus.inbox
    assert r.origin == ResourceOrigin.manual


async def test_resource_linked_to_project(store: DBStore):
    await _seed_project(store)
    r = await store.create_resource(ResourceCreate(
        type=ResourceType.note, title="Linked Note",
        project_ids=["proj-1"],
    ))
    resources = await store.list_resources(project_id="proj-1")
    assert any(res.id == r.id for res in resources)


async def test_update_resource_status_to_reading(store: DBStore):
    await _seed_project(store)
    r = await store.create_resource(ResourceCreate(
        type=ResourceType.article, title="Status Test",
        project_ids=["proj-1"],
    ))
    assert r.status == ResourceStatus.inbox

    updated = await store.update_resource(r.id, ResourceUpdate(status=ResourceStatus.reading))
    assert updated is not None
    assert updated.status == ResourceStatus.reading


async def test_update_resource_status_to_processed(store: DBStore):
    await _seed_project(store)
    r = await store.create_resource(ResourceCreate(
        type=ResourceType.article, title="Full Cycle",
        project_ids=["proj-1"],
    ))
    await store.update_resource(r.id, ResourceUpdate(status=ResourceStatus.reading))
    final = await store.update_resource(r.id, ResourceUpdate(status=ResourceStatus.processed))
    assert final.status == ResourceStatus.processed


async def test_update_resource_not_found(store: DBStore):
    result = await store.update_resource("nonexistent-id", ResourceUpdate(status=ResourceStatus.reading))
    assert result is None


# ── Proposals ─────────────────────────────────────────────────────────────────

async def _seed_proposal(store: DBStore):
    await _seed_project(store)
    return await store.create_proposal(ProposalCreate(**make_proposal_payload()))


async def test_create_proposal(store: DBStore):
    p = await _seed_proposal(store)
    assert p.title == "Deep dive into async Python"
    assert p.status == "pending"
    assert p.takeaways == ["Use asyncio", "Avoid blocking calls", "Test with pytest-asyncio"]


async def test_list_proposals_by_project(store: DBStore):
    await _seed_proposal(store)
    proposals = await store.list_proposals(project_id="proj-1", status="pending")
    assert len(proposals) == 1
    assert proposals[0].gap_label == "async patterns"


async def test_list_proposals_empty_for_other_project(store: DBStore):
    await _seed_proposal(store)
    proposals = await store.list_proposals(project_id="other-proj", status="pending")
    assert proposals == []


async def test_accept_proposal_creates_resource(store: DBStore):
    p = await _seed_proposal(store)
    resource = await store.accept_proposal(p.id)

    assert resource is not None
    assert resource.title == "Deep dive into async Python"
    assert resource.origin == ResourceOrigin.suggested
    assert resource.status == ResourceStatus.inbox


async def test_accept_proposal_stores_why_relevant(store: DBStore):
    """description field must carry why_relevant so the inbox can display it."""
    p = await _seed_proposal(store)
    resource = await store.accept_proposal(p.id)

    assert resource.description == "Directly relevant to the async architecture decisions."


async def test_accept_proposal_stores_takeaways_in_content(store: DBStore):
    """takeaways must be stored as JSON in content so the inbox row can render them."""
    p = await _seed_proposal(store)
    resource = await store.accept_proposal(p.id)

    takeaways = json.loads(resource.content)
    assert isinstance(takeaways, list)
    assert "Use asyncio" in takeaways
    assert len(takeaways) == 3


async def test_accept_proposal_marks_it_accepted(store: DBStore):
    p = await _seed_proposal(store)
    await store.accept_proposal(p.id)

    # Proposal should no longer be in pending list
    pending = await store.list_proposals(project_id="proj-1", status="pending")
    assert all(pr.id != p.id for pr in pending)


async def test_accept_proposal_twice_returns_none(store: DBStore):
    """Accepting an already-accepted proposal is a no-op."""
    p = await _seed_proposal(store)
    await store.accept_proposal(p.id)
    result = await store.accept_proposal(p.id)
    assert result is None


async def test_dismiss_proposal(store: DBStore):
    p = await _seed_proposal(store)
    ok = await store.dismiss_proposal(p.id)
    assert ok is True

    pending = await store.list_proposals(project_id="proj-1", status="pending")
    assert all(pr.id != p.id for pr in pending)


async def test_dismiss_nonexistent_proposal(store: DBStore):
    result = await store.dismiss_proposal("nonexistent-id")
    assert result is False


# ── Decisions ─────────────────────────────────────────────────────────────────

async def test_create_decision(store: DBStore):
    await _seed_project(store)
    d = await store.create_decision("proj-1", DecisionCreate(
        title="Use PostgreSQL",
        type="adr",
        context="Need a reliable relational DB",
        body="Chose PostgreSQL for ACID compliance.",
        consequences="Need to manage schema migrations.",
        alternatives=[],
    ))
    assert d.title == "Use PostgreSQL"
    assert d.project_id == "proj-1"


# ── Concepts ──────────────────────────────────────────────────────────────────

async def test_create_concept(store: DBStore):
    await _seed_project(store)
    c = await store.create_concept("proj-1", ConceptCreate(
        name="Async IO", desc="Non-blocking I/O patterns"
    ))
    assert c.name == "Async IO"
    assert c.project_id == "proj-1"
