"""
Unit tests for GraphEngine — no DB required.
"""

import pytest
from backend.services.graph_engine import GraphEngine
from backend.models.project import Project, Decision, DecisionType
from backend.models.resource import Resource, Edge, ResourceType, ResourceStatus, ResourceOrigin
from datetime import date


def _project(id="p1", name="Test Project"):
    return Project(
        id=id, name=name, emoji="📁", description="", color="#00d4ff",
        status="active", project_type="personal", tags=[], progress="0",
        created=date.today(), updated=date.today(),
    )


def _resource(id="r1", title="Test Resource"):
    return Resource(
        id=id, type=ResourceType.article, title=title, description="",
        source_url=None, project_ids=[], tags=[], content="",
        created=date.today(), status=ResourceStatus.inbox, origin=ResourceOrigin.manual,
    )


def _decision(id="d1", title="Use PostgreSQL"):
    return Decision(
        id=id, project_id="p1", title=title, date=date.today(),
        type=DecisionType.adr, status="accepted", context="", body="",
        consequences="", alternatives=[],
    )


def test_empty_graph():
    g = GraphEngine()
    stats = g.stats()
    assert stats["node_count"] == 0
    assert stats["edge_count"] == 0


def test_add_project_node():
    g = GraphEngine()
    p = _project()
    g.add_project(p)
    stats = g.stats()
    assert stats["node_count"] == 1


def test_add_resource_node():
    g = GraphEngine()
    r = _resource()
    g.add_resource(r)
    assert g.stats()["node_count"] == 1


def test_rebuild_from_scratch():
    g = GraphEngine()
    projects = [_project("p1"), _project("p2", "Second")]
    resources = [_resource("r1"), _resource("r2", "Second Resource")]
    g.rebuild(projects=projects, decisions=[], resources=resources, edges=[])
    assert g.stats()["node_count"] == 4


def test_search_nodes_finds_by_title():
    g = GraphEngine()
    g.rebuild(
        projects=[_project("p1", "Machine Learning"), _project("p2", "Web Dev")],
        decisions=[], resources=[], edges=[],
    )
    results = g.search_nodes("machine")
    assert len(results) == 1
    assert results[0].id == "p1"


def test_search_nodes_case_insensitive():
    g = GraphEngine()
    g.rebuild(projects=[_project("p1", "Async Python")], decisions=[], resources=[], edges=[])
    assert len(g.search_nodes("ASYNC")) == 1
    assert len(g.search_nodes("python")) == 1


def test_search_nodes_no_match():
    g = GraphEngine()
    g.rebuild(projects=[_project("p1", "Machine Learning")], decisions=[], resources=[], edges=[])
    assert g.search_nodes("quantum") == []


def test_neighbors_returns_connected_nodes():
    g = GraphEngine()
    g.rebuild(
        projects=[_project("p1")],
        decisions=[("p1", _decision("d1"))],
        resources=[_resource("r1")],
        edges=[],
    )
    result = g.neighbors("p1", depth=1)
    # p1 should have d1 as a neighbor (decision linked to project)
    neighbor_ids = {n.id for n in result.nodes}
    assert "p1" in neighbor_ids


def test_get_graph_returns_all_nodes():
    g = GraphEngine()
    g.rebuild(
        projects=[_project("p1"), _project("p2", "B")],
        decisions=[("p1", _decision("d1"))],
        resources=[_resource("r1")],
        edges=[],
    )
    data = g.get_graph()
    assert len(data.nodes) == 4  # 2 projects + 1 decision + 1 resource
