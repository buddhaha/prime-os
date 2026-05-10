"""Resource, Edge, and Proposal models."""

from datetime import date as Date
from enum import Enum

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Resource
# ─────────────────────────────────────────────

class ResourceType(str, Enum):
    article  = "article"
    note     = "note"
    pdf      = "pdf"
    video    = "video"
    artifact = "artifact"
    link     = "link"


class ResourceStatus(str, Enum):
    inbox     = "inbox"      # added but not yet read
    reading   = "reading"    # actively in progress
    processed = "processed"  # read, extracted, linked
    archived  = "archived"   # done, no longer active


class ResourceOrigin(str, Enum):
    manual    = "manual"     # user added it directly
    suggested = "suggested"  # PRIME proposed it, user accepted


RESOURCE_META: dict[str, dict[str, str]] = {
    "article":  {"badge": "ART",  "color": "#3b82f6"},
    "note":     {"badge": "NOTE", "color": "#10b981"},
    "pdf":      {"badge": "PDF",  "color": "#f59e0b"},
    "video":    {"badge": "VID",  "color": "#ec4899"},
    "artifact": {"badge": "OBJ",  "color": "#8b5cf6"},
    "link":     {"badge": "LINK", "color": "#6366f1"},
}


class Resource(BaseModel):
    id:          str
    type:        ResourceType
    title:       str
    description: str        = ""
    source_url:  str | None = None
    project_ids: list[str]  = Field(default_factory=list)
    tags:        list[str]  = Field(default_factory=list)
    content:     str        = ""
    created:     Date       = Field(default_factory=Date.today)
    status:      ResourceStatus = ResourceStatus.inbox
    origin:      ResourceOrigin = ResourceOrigin.manual


class ResourceCreate(BaseModel):
    type:        ResourceType
    title:       str
    description: str        = ""
    source_url:  str | None = None
    project_ids: list[str]  = Field(default_factory=list)
    tags:        list[str]  = Field(default_factory=list)
    content:     str        = ""
    status:      ResourceStatus = ResourceStatus.inbox
    origin:      ResourceOrigin = ResourceOrigin.manual


class ResourceUpdate(BaseModel):
    title:       str | None             = None
    description: str | None             = None
    project_ids: list[str] | None       = None
    tags:        list[str] | None       = None
    status:      ResourceStatus | None  = None
    content:     str | None             = None


# ─────────────────────────────────────────────
# Graph edges
# ─────────────────────────────────────────────

class RelationType(str, Enum):
    contains   = "contains"
    references = "references"
    cites      = "cites"
    related_to = "related_to"
    supersedes = "supersedes"


class Edge(BaseModel):
    id:       str
    from_id:  str
    to_id:    str
    relation: RelationType = RelationType.related_to
    note:     str = ""


class EdgeCreate(BaseModel):
    from_id:  str
    to_id:    str
    relation: RelationType = RelationType.related_to
    note:     str = ""


# ─────────────────────────────────────────────
# Proposals — PRIME OS suggested resources
# ─────────────────────────────────────────────

class ProposalStatus(str, Enum):
    pending   = "pending"
    accepted  = "accepted"
    dismissed = "dismissed"


class Proposal(BaseModel):
    id:            str
    project_id:    str
    title:         str
    resource_type: ResourceType
    source_url:    str | None = None
    read_time:     str | None = None   # e.g. "18 min read"
    why_relevant:  str        = ""     # 2-3 sentences of project-specific context
    takeaways:     list[str]  = Field(default_factory=list)  # 3 bullet points
    gap_type:      str        = ""     # "concept" | "todo" | "decision"
    gap_label:     str        = ""     # name of the concept/todo that triggered this
    status:        ProposalStatus = ProposalStatus.pending
    created:       Date       = Field(default_factory=Date.today)


class ProposalCreate(BaseModel):
    project_id:    str
    title:         str
    resource_type: ResourceType
    source_url:    str | None = None
    read_time:     str | None = None
    why_relevant:  str        = ""
    takeaways:     list[str]  = Field(default_factory=list)
    gap_type:      str        = ""
    gap_label:     str        = ""
