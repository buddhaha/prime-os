"""
Project, Decision (ADR), and Todo models.

On disk layout:
  ~/PRIME/projects/{slug}/
    project.json          ← Project metadata
    decisions/
      ADR-001-title.md    ← Markdown with YAML frontmatter
    todos.json            ← list of Todo objects
    concepts.json         ← list of {name, desc} dicts
"""

from datetime import date as Date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class ProjectStatus(str, Enum):
    active   = "active"
    planning = "planning"
    on_hold  = "on_hold"
    archived = "archived"


class ProjectType(str, Enum):
    personal    = "personal"    # Side project, learning, experiments
    capability  = "capability"  # IBM offering/demo being built out
    opportunity = "opportunity" # Active client deal or engagement
    knowledge   = "knowledge"   # Persistent reference area (product knowledge, certifications)


class DecisionType(str, Enum):
    adr       = "adr"        # Architectural Decision Record
    decision  = "decision"   # Lighter-weight decision
    milestone = "milestone"
    note      = "note"


class DecisionStatus(str, Enum):
    proposed  = "proposed"
    accepted  = "accepted"
    deprecated = "deprecated"
    superseded = "superseded"


class TodoStatus(str, Enum):
    open      = "open"
    done      = "done"
    cancelled = "cancelled"


class Priority(str, Enum):
    high   = "high"
    medium = "medium"
    low    = "low"


# ─────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────

class Project(BaseModel):
    """Stored as ~/PRIME/projects/{id}/project.json"""
    id:           str
    name:         str
    emoji:        str   = "📁"
    description:  str   = ""
    color:        str   = "#00d4ff"
    status:       ProjectStatus = ProjectStatus.active
    project_type: ProjectType   = ProjectType.personal
    tags:         list[str]     = Field(default_factory=list)
    created: Date = Field(default_factory=Date.today)
    updated: Date = Field(default_factory=Date.today)

    # Derived — populated by FileStore, not stored in project.json
    decision_count: int = 0
    todo_count:     int = 0
    resource_count: int = 0
    progress:       int = 0   # 0-100, computed from todos


class ProjectCreate(BaseModel):
    name:         str
    emoji:        str  = "📁"
    description:  str  = ""
    color:        str  = "#00d4ff"
    status:       ProjectStatus = ProjectStatus.active
    project_type: ProjectType   = ProjectType.personal
    tags:         list[str]     = Field(default_factory=list)


# ─────────────────────────────────────────────
# Decision / ADR
# ─────────────────────────────────────────────

class Alternative(BaseModel):
    title:  str
    reason: str   # why it was not chosen


class Decision(BaseModel):
    """
    Stored as Markdown with YAML frontmatter.
    File: ~/PRIME/projects/{project_id}/decisions/{id}.md

    Frontmatter keys:
      id, project, title, date, type, status, alternatives
    Body is free-form Markdown split into ## sections:
      Context, Decision, Consequences
    """
    id:           str
    project_id:   str
    title:        str
    date: Date = Field(default_factory=Date.today)
    type:         DecisionType   = DecisionType.decision
    status:       DecisionStatus = DecisionStatus.accepted
    context:      str = ""
    body:         str = ""
    consequences: str = ""
    alternatives: list[Alternative] = Field(default_factory=list)
    tags:         list[str]         = Field(default_factory=list)

    @property
    def slug(self) -> str:
        safe = self.title.lower().replace(" ", "-")
        safe = "".join(c for c in safe if c.isalnum() or c == "-")
        return f"{self.id}-{safe}"


class DecisionCreate(BaseModel):
    project_id:   str
    title:        str
    type:         DecisionType   = DecisionType.decision
    context:      str = ""
    body:         str = ""
    consequences: str = ""
    alternatives: list[Alternative] = Field(default_factory=list)
    tags:         list[str]         = Field(default_factory=list)


# ─────────────────────────────────────────────
# Todo
# ─────────────────────────────────────────────

class Todo(BaseModel):
    """Stored as items in ~/PRIME/projects/{project_id}/todos.json"""
    id:         str
    project_id: str
    text:       str
    status:     TodoStatus = TodoStatus.open
    priority:   Priority   = Priority.medium
    section:    str        = "Backlog"   # e.g. "In Progress", "Up Next"
    tags:       list[str]  = Field(default_factory=list)
    created: Date = Field(default_factory=Date.today)
    completed:  Date | None = None


class TodoCreate(BaseModel):
    text:     str
    priority: Priority = Priority.medium
    section:  str      = "Backlog"
    tags:     list[str] = Field(default_factory=list)


class TodoUpdate(BaseModel):
    status:   TodoStatus | None = None
    priority: Priority | None   = None
    section:  str | None        = None
    text:     str | None        = None


# ─────────────────────────────────────────────
# Concept
# ─────────────────────────────────────────────

class Concept(BaseModel):
    id:         str
    project_id: str
    name:       str
    desc:       str = ""
    tags:       list[str] = Field(default_factory=list)


class ConceptCreate(BaseModel):
    name: str
    desc: str = ""
    tags: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# Full project detail (returned by GET /projects/{id})
# ─────────────────────────────────────────────

class ProjectDetail(BaseModel):
    project:   Project
    decisions: list[Decision] = Field(default_factory=list)
    todos:     list[Todo]     = Field(default_factory=list)
    concepts:  list[Concept]  = Field(default_factory=list)
