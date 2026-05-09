"""
Resource model — any piece of content captured into the knowledge base.

On disk layout:
  ~/PRIME/knowledge/
    nodes.json          ← list of Resource objects (index)
    edges.json          ← list of Edge objects
    articles/           ← saved Markdown versions of web articles
    notes/              ← personal notes (.md)
    pdfs/               ← original PDF files
    videos/             ← metadata + transcript (.md)
    artifacts/          ← design files, exports, code, etc.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ResourceType(str, Enum):
    article  = "article"
    note     = "note"
    pdf      = "pdf"
    video    = "video"
    artifact = "artifact"


# Emoji and color associated with each type — used by graph + UI
RESOURCE_META: dict[ResourceType, dict[str, str]] = {
    ResourceType.article:  {"emoji": "📰", "color": "#3b82f6"},
    ResourceType.note:     {"emoji": "📝", "color": "#10b981"},
    ResourceType.pdf:      {"emoji": "📄", "color": "#f59e0b"},
    ResourceType.video:    {"emoji": "🎬", "color": "#ec4899"},
    ResourceType.artifact: {"emoji": "🎨", "color": "#8b5cf6"},
}


class Resource(BaseModel):
    """
    A node in the knowledge graph.
    Stored as an entry in ~/PRIME/knowledge/nodes.json.
    The actual content lives in the type-specific subdirectory.
    """
    id:          str
    type:        ResourceType
    title:       str
    description: str  = ""

    # Where the content lives on disk (relative to PRIME root)
    # e.g. "knowledge/articles/rdf-vs-property-graph.md"
    path:        str | None = None

    # Original source (URL for articles/videos, None for notes/artifacts)
    source_url:  str | None = None

    # Which projects reference this resource
    project_ids: list[str] = Field(default_factory=list)

    tags:        list[str]  = Field(default_factory=list)
    created:     datetime   = Field(default_factory=datetime.utcnow)
    updated:     datetime   = Field(default_factory=datetime.utcnow)

    # Derived — not stored
    @property
    def emoji(self) -> str:
        return RESOURCE_META[self.type]["emoji"]

    @property
    def color(self) -> str:
        return RESOURCE_META[self.type]["color"]


class ResourceCreate(BaseModel):
    type:        ResourceType
    title:       str
    description: str       = ""
    source_url:  str | None = None
    project_ids: list[str]  = Field(default_factory=list)
    tags:        list[str]  = Field(default_factory=list)
    content:     str        = ""   # initial text content (for notes/articles)


class ResourceUpdate(BaseModel):
    title:       str | None        = None
    description: str | None        = None
    project_ids: list[str] | None  = None
    tags:        list[str] | None  = None


# ─────────────────────────────────────────────
# Graph edge — relationship between any two nodes
# ─────────────────────────────────────────────

class RelationType(str, Enum):
    # project ↔ resource
    contains    = "contains"    # project → resource (owns it)
    references  = "references"  # resource → resource (cites/links)
    # decision ↔ resource
    cites       = "cites"
    # general
    related_to  = "related_to"
    supersedes  = "supersedes"


class Edge(BaseModel):
    """
    A directed edge in the knowledge graph.
    Stored in ~/PRIME/knowledge/edges.json.
    Both 'from_id' and 'to_id' can be project IDs, resource IDs, or decision IDs.
    """
    id:       str
    from_id:  str
    to_id:    str
    relation: RelationType = RelationType.related_to
    note:     str = ""   # optional human label on the edge


class EdgeCreate(BaseModel):
    from_id:  str
    to_id:    str
    relation: RelationType = RelationType.related_to
    note:     str = ""
