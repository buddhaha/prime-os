"""
Graph models — the shape of data returned by GET /api/graph.
These are the wire types; the in-memory graph uses NetworkX internally.
"""

from typing import Any
from pydantic import BaseModel


class GraphNode(BaseModel):
    """
    A node as returned to the frontend.
    'type' drives color + emoji in the visualisation.
    """
    id:          str
    label:       str
    type:        str          # "project" | "article" | "note" | "pdf" | "video" | "artifact" | "decision"
    emoji:       str
    color:       str
    description: str  = ""
    tags:        list[str] = []
    # Physics hint: larger nodes repel more / render bigger
    weight:      int  = 1     # 1=leaf, 2=resource, 3=project hub


class GraphEdge(BaseModel):
    id:       str
    source:   str
    target:   str
    relation: str   # human-readable relation type
    label:    str = ""


class GraphData(BaseModel):
    """Full graph payload — fetched once on load, then streamed diffs via WS."""
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    node_count: int
    edge_count: int

    @classmethod
    def empty(cls) -> "GraphData":
        return cls(nodes=[], edges=[], node_count=0, edge_count=0)
