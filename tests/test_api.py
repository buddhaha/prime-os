"""
HTTP-layer tests for PRIME OS API endpoints.
Uses AsyncClient with dependency overrides — lifespan does NOT run.
Tables are truncated before each test (via autouse `isolate` fixture).
"""

import pytest
from httpx import AsyncClient
from tests.conftest import project_create


# ── Health ────────────────────────────────────────────────────────────────────

async def test_health(client: AsyncClient):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Projects ──────────────────────────────────────────────────────────────────

async def test_list_projects_empty(client: AsyncClient):
    r = await client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


async def test_create_project(client: AsyncClient):
    r = await client.post("/api/projects", json={"name": "My Project", "emoji": "🚀"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "My Project"
    assert data["emoji"] == "🚀"
    assert "id" in data  # UUID generated server-side


async def test_create_project_then_list(client: AsyncClient):
    await client.post("/api/projects", json={"name": "Listed Project"})
    r = await client.get("/api/projects")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "Listed Project"


async def test_get_project_detail(client: AsyncClient):
    create_r = await client.post("/api/projects", json={"name": "Detail Project"})
    project_id = create_r.json()["id"]

    r = await client.get(f"/api/projects/{project_id}")
    assert r.status_code == 200
    data = r.json()
    assert "project" in data
    assert data["project"]["id"] == project_id
    assert data["decisions"] == []
    assert data["todos"] == []


async def test_get_project_not_found(client: AsyncClient):
    r = await client.get("/api/projects/does-not-exist")
    assert r.status_code == 404


# ── Resources ─────────────────────────────────────────────────────────────────

async def _create_project_and_resource(client: AsyncClient):
    """Helper: create a project then a resource linked to it."""
    proj = await client.post("/api/projects", json={"name": "Parent Project"})
    project_id = proj.json()["id"]
    res = await client.post("/api/resources", json={
        "type": "article",
        "title": "Test Article",
        "description": "Interesting read",
        "source_url": "https://example.com",
        "project_ids": [project_id],
    })
    return project_id, res


async def test_create_resource(client: AsyncClient):
    _, r = await _create_project_and_resource(client)
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Test Article"
    assert data["status"] == "inbox"
    assert data["origin"] == "manual"


async def test_create_resource_default_status_is_inbox(client: AsyncClient):
    proj = await client.post("/api/projects", json={"name": "P"})
    r = await client.post("/api/resources", json={
        "type": "note",
        "title": "Quick note",
        "project_ids": [proj.json()["id"]],
    })
    assert r.status_code == 201
    assert r.json()["status"] == "inbox"


async def test_patch_resource_status_to_reading(client: AsyncClient):
    _, create = await _create_project_and_resource(client)
    resource_id = create.json()["id"]
    r = await client.patch(f"/api/resources/{resource_id}", json={"status": "reading"})
    assert r.status_code == 200
    assert r.json()["status"] == "reading"


async def test_patch_resource_status_to_processed(client: AsyncClient):
    _, create = await _create_project_and_resource(client)
    resource_id = create.json()["id"]
    await client.patch(f"/api/resources/{resource_id}", json={"status": "reading"})
    r = await client.patch(f"/api/resources/{resource_id}", json={"status": "processed"})
    assert r.status_code == 200
    assert r.json()["status"] == "processed"


async def test_patch_resource_not_found(client: AsyncClient):
    r = await client.patch("/api/resources/nonexistent", json={"status": "reading"})
    assert r.status_code == 404


# ── Proposals ─────────────────────────────────────────────────────────────────

async def test_list_proposals_empty(client: AsyncClient):
    proj = await client.post("/api/projects", json={"name": "P"})
    r = await client.get(f"/api/proposals?project_id={proj.json()['id']}&status=pending")
    assert r.status_code == 200
    assert r.json() == []


async def test_dismiss_proposal_returns_404_for_missing(client: AsyncClient):
    r = await client.delete("/api/proposals/nonexistent-id")
    assert r.status_code == 404


async def test_accept_proposal_returns_404_for_missing(client: AsyncClient):
    r = await client.post("/api/proposals/nonexistent-id/accept")
    assert r.status_code == 404


# ── Graph ─────────────────────────────────────────────────────────────────────

async def test_graph_endpoint_returns_data(client: AsyncClient):
    r = await client.get("/api/graph")
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert "edges" in data


async def test_graph_stats_endpoint(client: AsyncClient):
    r = await client.get("/api/graph/stats")
    assert r.status_code == 200
    stats = r.json()
    assert "node_count" in stats
    assert "edge_count" in stats


async def test_graph_search_returns_list(client: AsyncClient):
    r = await client.get("/api/graph/search?q=anything")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
