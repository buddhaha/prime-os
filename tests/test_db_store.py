"""
Integration tests for DBStore — run against prime_test Postgres DB,
rolled back automatically after each test.
"""

import json
from datetime import datetime

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

from backend.services.db_store import DBStore
from backend.models.project import DecisionCreate, ConceptCreate
from backend.models.resource import (
    ResourceUpdate, ResourceStatus, ResourceOrigin,
)
from backend.models.agent import RunStatus, LogEntry, LogLevel
from tests.conftest import project_create, resource_create, proposal_create, agent_run_create


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


# ── Agent runs ────────────────────────────────────────────────────────────────

async def test_create_run(store: DBStore):
    run = await store.create_run(agent_run_create())
    assert run.id == "run-test-01"
    assert run.agent_id == "researcher"
    assert run.status == RunStatus.running


async def test_get_run(store: DBStore):
    await store.create_run(agent_run_create())
    fetched = await store.get_run("run-test-01")
    assert fetched is not None
    assert fetched.task == "Summarise active projects"


async def test_get_run_not_found(store: DBStore):
    result = await store.get_run("nonexistent-run")
    assert result is None


async def test_update_run_status(store: DBStore):
    await store.create_run(agent_run_create())
    await store.update_run("run-test-01", {"status": RunStatus.completed, "progress": 100})
    run = await store.get_run("run-test-01")
    assert run.status == RunStatus.completed
    assert run.progress == 100


async def test_list_runs_returns_created(store: DBStore):
    await store.create_run(agent_run_create(id="r1", agent_id="researcher"))
    await store.create_run(agent_run_create(id="r2", agent_id="writer"))
    runs = await store.list_runs()
    ids = {r.id for r in runs}
    assert "r1" in ids and "r2" in ids


async def test_list_runs_filtered_by_agent(store: DBStore):
    await store.create_run(agent_run_create(id="r1", agent_id="researcher"))
    await store.create_run(agent_run_create(id="r2", agent_id="writer"))
    runs = await store.list_runs(agent_id="writer")
    assert all(r.agent_id == "writer" for r in runs)
    assert len(runs) == 1


async def test_list_runs_filtered_by_status(store: DBStore):
    await store.create_run(agent_run_create(id="r1", status=RunStatus.running))
    await store.create_run(agent_run_create(id="r2", status=RunStatus.completed))
    await store.update_run("r2", {"status": RunStatus.completed})
    runs = await store.list_runs(status="running")
    assert all(r.status == RunStatus.running for r in runs)


async def test_append_and_get_logs(store: DBStore):
    await store.create_run(agent_run_create())
    await store.append_log("run-test-01", LogEntry(level=LogLevel.info, message="Starting"))
    await store.append_log("run-test-01", LogEntry(level=LogLevel.ok,   message="Done"))
    logs = await store.get_run_logs("run-test-01")
    assert len(logs) == 2
    assert logs[0].message == "Starting"
    assert logs[1].level == LogLevel.ok


async def test_get_logs_empty_for_unknown_run(store: DBStore):
    logs = await store.get_run_logs("no-such-run")
    assert logs == []


async def test_get_resource_by_id(store: DBStore):
    p = await _make_project(store)
    r = await _make_resource(store, p.id, title="My Article")
    fetched = await store.get_resource(r.id)
    assert fetched is not None
    assert fetched.title == "My Article"


async def test_get_resource_not_found(store: DBStore):
    result = await store.get_resource("nonexistent")
    assert result is None


async def test_read_resource_content(store: DBStore):
    from backend.models.resource import ResourceCreate, ResourceType
    p = await _make_project(store)
    r = await store.create_resource(ResourceCreate(
        type=ResourceType.note,
        title="Note with content",
        content="Hello world",
        project_ids=[p.id],
    ))
    content = await store.read_resource_content(r.id)
    assert content == "Hello world"


async def test_read_resource_content_empty(store: DBStore):
    p = await _make_project(store)
    r = await _make_resource(store, p.id)   # no content set
    content = await store.read_resource_content(r.id)
    assert content is None or content == ""
