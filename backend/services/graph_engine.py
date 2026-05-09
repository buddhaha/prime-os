"""
GraphEngine — builds and queries the in-memory knowledge graph.

Uses NetworkX as the graph data structure. The graph is rebuilt from
the filesystem on startup and incrementally updated as resources/edges
are added. A cached JSON export is served to the frontend.

Node ID conventions:
  - Projects:  project ID  (e.g. "personal-ai-os")
  - Decisions: "{project_id}::{decision_id}" (e.g. "personal-ai-os::ADR-001")
  - Resources: resource UUID (e.g. "a1b2c3d4")
"""
from __future__ import annotations

import networkx as nx

from ..models.graph import GraphNode, GraphEdge, GraphData
from ..models.project import Project, Decision, DecisionType
from ..models.resource import Resource, Edge, RESOURCE_META, ResourceType

# Colors + emoji per node type
PROJECT_COLOR   = "#00d4ff"
DECISION_COLORS = {
    DecisionType.adr:       "#3b82f6",
    DecisionType.decision:  "#00d4ff",
    DecisionType.milestone: "#10b981",
    DecisionType.note:      "#64748b",
}


class GraphEngine:
    """
    Wraps a NetworkX DiGraph and produces the wire format for the frontend.
    Call rebuild() to re-scan from the FileStore; the result is cached.
    """

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()
        self._graph_data: GraphData = GraphData.empty()

    # ─────────────────────────────────────────
    # Build / rebuild
    # ─────────────────────────────────────────

    def rebuild(
        self,
        projects:   list[Project],
        decisions:  list[tuple[str, Decision]],   # (project_id, decision)
        resources:  list[Resource],
        edges:      list[Edge],
    ) -> GraphData:
        """
        Full rebuild from FileStore data. Called on startup and after
        any structural change (add project / resource / edge).
        """
        g = nx.DiGraph()

        # ── Project nodes
        for proj in projects:
            g.add_node(
                proj.id,
                label=proj.name,
                type="project",
                emoji="📁",
                color=PROJECT_COLOR,
                description=proj.description,
                tags=proj.tags,
                weight=3,
            )

        # ── Decision nodes + auto-edges to their project
        for project_id, dec in decisions:
            node_id = f"{project_id}::{dec.id}"
            color   = DECISION_COLORS.get(dec.type, "#64748b")
            emoji   = {"adr": "🏛", "decision": "⚖️", "milestone": "🏁", "note": "📌"}.get(dec.type.value, "📌")
            g.add_node(
                node_id,
                label=dec.id,
                type=f"decision_{dec.type.value}",
                emoji=emoji,
                color=color,
                description=dec.title,
                tags=dec.tags,
                weight=2,
            )
            g.add_edge(project_id, node_id, relation="has_decision", label="")

        # ── Resource nodes
        for res in resources:
            meta = RESOURCE_META.get(res.type, {})
            g.add_node(
                res.id,
                label=res.title,
                type=res.type.value,
                emoji=meta.get("emoji", "📄"),
                color=meta.get("color", "#64748b"),
                description=res.description,
                tags=res.tags,
                weight=2,
            )

        # ── Explicit edges (from edges.json)
        for edge in edges:
            if g.has_node(edge.from_id) and g.has_node(edge.to_id):
                g.add_edge(
                    edge.from_id,
                    edge.to_id,
                    id=edge.id,
                    relation=edge.relation.value,
                    label=edge.note or edge.relation.value,
                )

        self._g = g
        self._graph_data = self._to_wire_format()
        return self._graph_data

    def _to_wire_format(self) -> GraphData:
        nodes = []
        for node_id, attrs in self._g.nodes(data=True):
            nodes.append(GraphNode(
                id=node_id,
                label=attrs.get("label", node_id),
                type=attrs.get("type", "unknown"),
                emoji=attrs.get("emoji", "●"),
                color=attrs.get("color", "#64748b"),
                description=attrs.get("description", ""),
                tags=attrs.get("tags") or [],
                weight=attrs.get("weight", 1),
            ))

        edges = []
        for i, (src, tgt, attrs) in enumerate(self._g.edges(data=True)):
            edges.append(GraphEdge(
                id=attrs.get("id", f"e{i}"),
                source=src,
                target=tgt,
                relation=attrs.get("relation", "related_to"),
                label=attrs.get("label", ""),
            ))

        return GraphData(
            nodes=nodes,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
        )

    # ─────────────────────────────────────────
    # Incremental updates (no full rebuild)
    # ─────────────────────────────────────────

    def add_project(self, proj: Project) -> None:
        self._g.add_node(
            proj.id,
            label=proj.name, type="project", emoji="📁",
            color=PROJECT_COLOR, description=proj.description,
            tags=proj.tags, weight=3,
        )
        self._graph_data = self._to_wire_format()

    def add_resource(self, res: Resource) -> None:
        meta = RESOURCE_META.get(res.type, {})
        self._g.add_node(
            res.id,
            label=res.title,
            type=res.type.value,
            emoji=meta.get("emoji", "📄"),
            color=meta.get("color", "#64748b"),
            description=res.description,
            tags=res.tags,
            weight=2,
        )
        self._graph_data = self._to_wire_format()

    def add_edge(self, edge: Edge) -> None:
        if self._g.has_node(edge.from_id) and self._g.has_node(edge.to_id):
            self._g.add_edge(
                edge.from_id, edge.to_id,
                id=edge.id,
                relation=edge.relation.value,
                label=edge.note or edge.relation.value,
            )
            self._graph_data = self._to_wire_format()

    # ─────────────────────────────────────────
    # Queries
    # ─────────────────────────────────────────

    def get_graph(self) -> GraphData:
        """Return the cached wire-format graph."""
        return self._graph_data

    def neighbors(self, node_id: str, depth: int = 1) -> GraphData:
        """Return the subgraph within `depth` hops of `node_id`."""
        if node_id not in self._g:
            return GraphData.empty()
        reachable = {node_id}
        frontier = {node_id}
        for _ in range(depth):
            next_frontier = set()
            for n in frontier:
                next_frontier |= set(self._g.predecessors(n))
                next_frontier |= set(self._g.successors(n))
            frontier = next_frontier - reachable
            reachable |= frontier

        sub = self._g.subgraph(reachable).copy()
        engine = GraphEngine()
        engine._g = sub
        return engine._to_wire_format()

    def search_nodes(self, query: str) -> list[GraphNode]:
        """Simple label / description / tag substring match."""
        q = query.lower()
        results = []
        for node_id, attrs in self._g.nodes(data=True):
            label = attrs.get("label", "").lower()
            desc  = attrs.get("description", "").lower()
            tags  = " ".join(attrs.get("tags") or []).lower()
            if q in label or q in desc or q in tags:
                results.append(GraphNode(
                    id=node_id,
                    label=attrs.get("label", node_id),
                    type=attrs.get("type", "unknown"),
                    emoji=attrs.get("emoji", "●"),
                    color=attrs.get("color", "#64748b"),
                    description=attrs.get("description", ""),
                    tags=attrs.get("tags") or [],
                    weight=attrs.get("weight", 1),
                ))
        return results

    def stats(self) -> dict:
        return {
            "node_count": self._g.number_of_nodes(),
            "edge_count": self._g.number_of_edges(),
            "connected_components": nx.number_weakly_connected_components(self._g),
            "most_connected": sorted(
                [(n, self._g.degree(n)) for n in self._g.nodes()],
                key=lambda x: -x[1],
            )[:5],
        }
