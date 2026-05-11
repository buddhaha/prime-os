"""
Integration tests for DBStore — run against prime_test Postgres DB,
rolled back automatically after each test.
"""

import json
import pytest

from backend.services.db_store import DBStore
from backend.models.project import DecisionCreate, ConceptCreate
from backend.models.resource import (
    ResourceUpdate, ResourceStatus, ResourceOrigin,
)
from tests.conftest import project_create, resource_create, proposal_create


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _make_project(store: DBStore, **kwargs):
    return await store.create_project(project_create(**kwargs))


async def _make_resource(store: DBStore, project_id: str, **kwargs):
    return await store.create_resource(resource_create(project_id, **kwargs))


async def _make_proposal(store: DBStore, project_id: str, **kwargs):
    return await store.create_proposal(proposal_create(project_id, **kwargs))


# ── Projects ──────────────────────────────────────────────────────────────────

async def test_create_project_returns_project(store: DBStore):
    p = await _make_project(store)
    assert p.id  # UUID generated
    assert p.name == "Test Project"


async def test_create_project_has_zero_counts(store: DBStore):
    p = await _make_project(store)
    assert p.todo_count == 0
    assert p.decision_count == 0
    assert p.resource_count == 0


async def test_list_projects_includes_created(store: DBStore):
    p = await _make_project(store, name="List Me")
    projects = await store.list_projects()
    assert any(proj.id == p.id for proj in projects)


async def test_get_project_detail(store: DBStore):
    p = await _make_project(store, name="Detailed")
    detail = await store.get_project_detail(p.id)
    assert detail is not None
    assert detail.project.name == "Detailed"
    assert detail.decisions == []
    assert detail.todos == []


async def test_get_project_detail_not_found(store: DBStore):
    result = await store.get_project_detail("nonexistent-id")
    assert result is None


# ── Resources ─────────────────────────────────────────────────────────────────

async def test_create_resource_defaults(store: DBStore):
    p = await _make_project(store)
    r = await _make_resource(store, p.id)
    assert r.title == "Test Resource"
    assert r.status == ResourceStatus.inbox
    assert r.origin == ResourceOrigin.manual


async def test_resource_linked_to_project(store: DBStore):
    p = await _make_project(store)
    r = await _make_resource(store, p.id)
    resources = await store.list_resources(project_id=p.id)
    assert any(res.id == r.id for res in resources)


async def test_resource_not_in_other_project(store: DBStore):
    p1 = await _make_project(store, name="P1")
    p2 = await _make_project(store, name="P2")
    await _make_resource(store, p1.id)
    resources = await store.list_resources(project_id=p2.id)
    assert resources == []


async def test_update_resource_status_reading(store: DBStore):
    p = await _make_project(store)
    r = await _make_resource(store, p.id)
    updated = await store.update_resource(r.id, ResourceUpdate(status=ResourceStatus.reading))
    assert updated.status == ResourceStatus.reading


async def test_update_resource_status_processed(store: DBStore):
    p = await _make_project(store)
    r = await _make_resource(store, p.id)
    await store.update_resource(r.id, ResourceUpdate(status=ResourceStatus.reading))
    final = await store.update_resource(r.id, ResourceUpdate(status=ResourceStatus.processed))
    assert final.status == ResourceStatus.processed


async def test_update_resource_not_found(store: DBStore):
    result = await store.update_resource("nonexistent", ResourceUpdate(status=ResourceStatus.reading))
    assert result is None


# ── Proposals ─────────────────────────────────────────────────────────────────

async def test_create_proposal(store: DBStore):
    p = await _make_project(store)
    prop = await _make_proposal(store, p.id)
    assert prop.title == "Deep dive into async Python"
    assert prop.status == "pending"
    assert prop.takeaways == ["Use asyncio", "Avoid blocking calls", "Test with pytest-asyncio"]


async def test_list_proposals_by_project(store: DBStore):
    p = await _make_project(store)
    await _make_proposal(store, p.id)
    proposals = await store.list_proposals(project_id=p.id, status="pending")
    assert len(proposals) == 1


async def test_list_proposals_empty_for_other_project(store: DBStore):
    p1 = await _make_project(store, name="P1")
    p2 = await _make_project(store, name="P2")
    await _make_proposal(store, p1.id)
    proposals = await store.list_proposals(project_id=p2.id, status="pending")
    assert proposals == []


async def test_accept_proposal_creates_resource(store: DBStore):
    p = await _make_project(store)
    prop = await _make_proposal(store, p.id)
    resource = await store.accept_proposal(prop.id)
    assert resource is not None
    assert resource.title == "Deep dive into async Python"
    assert resource.origin == ResourceOrigin.suggested
    assert resource.status == ResourceStatus.inbox


async def test_accept_proposal_stores_why_relevant_in_description(store: DBStore):
    """description must hold why_relevant so the inbox row can display it."""
    p = await _make_project(store)
    prop = await _make_proposal(store, p.id)
    resource = await store.accept_proposal(prop.id)
    assert resource.description == "Directly relevant to the async architecture decisions."


async def test_accept_proposal_stores_takeaways_as_json_in_content(store: DBStore):
    """takeaways must survive as a JSON list in content — this was a bug."""
    p = await _make_project(store)
    prop = await _make_proposal(store, p.id)
    resource = await store.accept_proposal(prop.id)
    takeaways = json.loads(resource.content)
    assert isinstance(takeaways, list)
    assert "Use asyncio" in takeaways
    assert len(takeaways) == 3


async def test_accept_proposal_removes_it_from_pending(store: DBStore):
    p = await _make_project(store)
    prop = await _make_proposal(store, p.id)
    await store.accept_proposal(prop.id)
    pending = await store.list_proposals(project_id=p.id, status="pending")
    assert all(pr.id != prop.id for pr in pending)


async def test_accept_proposal_twice_returns_none(store: DBStore):
    p = await _make_project(store)
    prop = await _make_proposal(store, p.id)
    await store.accept_proposal(prop.id)
    result = await store.accept_proposal(prop.id)
    assert result is None


async def test_dismiss_proposal(store: DBStore):
    p = await _make_project(store)
    prop = await _make_proposal(store, p.id)
    ok = await store.dismiss_proposal(prop.id)
    assert ok is True
    pending = await store.list_proposals(project_id=p.id, status="pending")
    assert all(pr.id != prop.id for pr in pending)


async def test_dismiss_nonexistent_returns_false(store: DBStore):
    result = await store.dismiss_proposal("nonexistent")
    assert result is False


# ── Decisions ─────────────────────────────────────────────────────────────────

async def test_create_decision(store: DBStore):
    p = await _make_project(store)
    d = await store.create_decision(DecisionCreate(
        project_id=p.id,
        title="Use PostgreSQL",
        type="adr",
        context="Need a reliable DB",
        body="Chose Postgres for ACID compliance.",
        consequences="Need to manage migrations.",
    ))
    assert d.title == "Use PostgreSQL"
    assert d.project_id == p.id


# ── Concepts ──────────────────────────────────────────────────────────────────

async def test_create_concept(store: DBStore):
    p = await _make_project(store)
    c = await store.create_concept(p.id, ConceptCreate(name="Async IO", desc="Non-blocking I/O"))
    assert c.name == "Async IO"
    assert c.project_id == p.id
