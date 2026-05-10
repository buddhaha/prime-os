"""
PRIME OS — PostgreSQL-backed store (replaces file_store.py).

Keeps the same public interface as FileStore so the API routers
don't need to change.
"""

from __future__ import annotations

from datetime import date
from typing import Any
import uuid

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import (
    ProjectRow, DecisionRow, TodoRow, ConceptRow, ResourceRow, EdgeRow,
    resource_projects,
)
from ..models.project import (
    Project, ProjectCreate, ProjectDetail,
    Decision, DecisionCreate,
    Todo, TodoCreate, TodoUpdate,
    Concept, ConceptCreate,
)
from ..models.resource import Resource, ResourceCreate, ResourceUpdate, Edge, EdgeCreate


def _new_id() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────
# Converters — ORM row → Pydantic model
# ─────────────────────────────────────────────

def _proj(row: ProjectRow) -> Project:
    return Project(
        id=row.id,
        name=row.name,
        emoji=row.emoji,
        description=row.description,
        color=row.color,
        status=row.status,
        project_type=row.project_type,
        tags=row.tags or [],
        progress=int(row.progress or 0),
        created=row.created,
        updated=row.updated,
        todo_count=len(row.todos) if row.todos is not None else 0,
        decision_count=len(row.decisions) if row.decisions is not None else 0,
        resource_count=len(row.resources) if row.resources is not None else 0,
    )


def _dec(row: DecisionRow) -> Decision:
    return Decision(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        date=row.date,
        type=row.type,
        status=row.status,
        context=row.context or "",
        body=row.body or "",
        consequences=row.consequences or "",
        alternatives=row.alternatives or [],
    )


def _todo(row: TodoRow) -> Todo:
    return Todo(
        id=row.id,
        project_id=row.project_id,
        text=row.text,
        status=row.status,
        priority=row.priority,
        section=row.section,
        tags=row.tags or [],
        created=row.created,
        completed=row.completed,
    )


def _concept(row: ConceptRow) -> Concept:
    return Concept(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        desc=row.desc or "",
    )


def _resource(row: ResourceRow) -> Resource:
    return Resource(
        id=row.id,
        type=row.type,
        title=row.title,
        description=row.description or "",
        source_url=row.source_url,
        tags=row.tags or [],
        content=row.content or "",
        created=row.created,
        project_ids=[p.id for p in row.projects] if row.projects is not None else [],
    )


def _edge(row: EdgeRow) -> Edge:
    return Edge(id=row.id, from_id=row.from_id, to_id=row.to_id, relation=row.relation, note=row.note or "")


# ─────────────────────────────────────────────
# DBStore
# ─────────────────────────────────────────────

class DBStore:
    """
    Async data-access layer backed by PostgreSQL.
    All public methods are async and accept/return Pydantic models.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Projects ───────────────────────────────

    async def list_projects(self) -> list[Project]:
        q = (
            select(ProjectRow)
            .options(
                selectinload(ProjectRow.todos),
                selectinload(ProjectRow.decisions),
                selectinload(ProjectRow.resources),
            )
            .order_by(ProjectRow.updated.desc())
        )
        rows = (await self.session.execute(q)).scalars().all()
        return [_proj(r) for r in rows]

    async def get_project_detail(self, project_id: str) -> ProjectDetail | None:
        q = (
            select(ProjectRow)
            .where(ProjectRow.id == project_id)
            .options(
                selectinload(ProjectRow.todos),
                selectinload(ProjectRow.decisions),
                selectinload(ProjectRow.concepts),
                selectinload(ProjectRow.resources),
            )
        )
        row = (await self.session.execute(q)).scalar_one_or_none()
        if not row:
            return None
        return ProjectDetail(
            project=_proj(row),
            decisions=[_dec(d) for d in row.decisions],
            todos=[_todo(t) for t in row.todos],
            concepts=[_concept(c) for c in row.concepts],
        )

    async def create_project(self, data: ProjectCreate) -> Project:
        row = ProjectRow(
            id=_new_id(),
            name=data.name,
            emoji=data.emoji,
            description=data.description,
            color=data.color,
            status=data.status.value,
            project_type=data.project_type.value,
            tags=data.tags,
            progress="0",
            created=date.today(),
            updated=date.today(),
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row, ["todos", "decisions", "resources"])
        return _proj(row)

    async def update_project(self, project_id: str, updates: dict) -> Project | None:
        q = (
            select(ProjectRow)
            .where(ProjectRow.id == project_id)
            .options(
                selectinload(ProjectRow.todos),
                selectinload(ProjectRow.decisions),
                selectinload(ProjectRow.resources),
            )
        )
        row = (await self.session.execute(q)).scalar_one_or_none()
        if not row:
            return None
        allowed = {"name","emoji","description","color","status","project_type","tags","progress"}
        for k, v in updates.items():
            if k in allowed:
                # enums arrive as strings from the API
                setattr(row, k, v.value if hasattr(v, "value") else v)
        row.updated = date.today()
        await self.session.flush()
        return _proj(row)

    # ── Decisions ──────────────────────────────

    async def list_decisions(self, project_id: str) -> list[Decision]:
        q = select(DecisionRow).where(DecisionRow.project_id == project_id).order_by(DecisionRow.date.desc())
        rows = (await self.session.execute(q)).scalars().all()
        return [_dec(r) for r in rows]

    async def create_decision(self, data: DecisionCreate) -> Decision:
        row = DecisionRow(
            id=_new_id(),
            project_id=data.project_id,
            title=data.title,
            date=data.date,
            type=data.type.value,
            status=data.status.value,
            context=data.context,
            body=data.body,
            consequences=data.consequences,
            alternatives=[a.model_dump() for a in (data.alternatives or [])],
        )
        self.session.add(row)
        await self.session.flush()
        return _dec(row)

    # ── Todos ──────────────────────────────────

    async def list_todos(self, project_id: str) -> list[Todo]:
        q = select(TodoRow).where(TodoRow.project_id == project_id)
        rows = (await self.session.execute(q)).scalars().all()
        return [_todo(r) for r in rows]

    async def create_todo(self, project_id: str, data: TodoCreate) -> Todo:
        row = TodoRow(
            id=_new_id(),
            project_id=project_id,
            text=data.text,
            status="open",
            priority=data.priority.value,
            section=data.section,
            tags=data.tags,
            created=date.today(),
        )
        self.session.add(row)
        await self.session.flush()
        return _todo(row)

    async def update_todo(self, project_id: str, todo_id: str, data: TodoUpdate) -> Todo | None:
        q = select(TodoRow).where(TodoRow.id == todo_id, TodoRow.project_id == project_id)
        row = (await self.session.execute(q)).scalar_one_or_none()
        if not row:
            return None
        if data.status is not None:
            row.status = data.status.value
            if data.status.value == "done" and not row.completed:
                row.completed = date.today()
        if data.priority is not None:
            row.priority = data.priority.value
        if data.section is not None:
            row.section = data.section
        await self.session.flush()
        # recalc project progress
        await self._recalc_progress(project_id)
        return _todo(row)

    async def _recalc_progress(self, project_id: str) -> None:
        q = select(TodoRow).where(TodoRow.project_id == project_id)
        todos = (await self.session.execute(q)).scalars().all()
        if todos:
            done = sum(1 for t in todos if t.status == "done")
            progress = int(done / len(todos) * 100)
        else:
            progress = 0
        q2 = select(ProjectRow).where(ProjectRow.id == project_id)
        proj = (await self.session.execute(q2)).scalar_one_or_none()
        if proj:
            proj.progress = str(progress)
            proj.updated  = date.today()

    # ── Concepts ───────────────────────────────

    async def list_concepts(self, project_id: str) -> list[Concept]:
        q = select(ConceptRow).where(ConceptRow.project_id == project_id)
        rows = (await self.session.execute(q)).scalars().all()
        return [_concept(r) for r in rows]

    async def create_concept(self, project_id: str, data: ConceptCreate) -> Concept:
        row = ConceptRow(
            id=_new_id(),
            project_id=project_id,
            name=data.name,
            desc=data.desc,
        )
        self.session.add(row)
        await self.session.flush()
        return _concept(row)

    # ── Resources ──────────────────────────────

    async def list_resources(self, project_id: str | None = None) -> list[Resource]:
        q = select(ResourceRow).options(selectinload(ResourceRow.projects))
        if project_id:
            q = q.join(resource_projects).where(resource_projects.c.project_id == project_id)
        rows = (await self.session.execute(q)).scalars().all()
        return [_resource(r) for r in rows]

    async def create_resource(self, data: ResourceCreate) -> Resource:
        row = ResourceRow(
            id=_new_id(),
            type=data.type.value,
            title=data.title,
            description=data.description,
            source_url=data.source_url,
            tags=data.tags,
            content=data.content,
            created=date.today(),
        )
        # link to projects
        if data.project_ids:
            proj_q = select(ProjectRow).where(ProjectRow.id.in_(data.project_ids))
            projs = (await self.session.execute(proj_q)).scalars().all()
            row.projects = projs
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row, ["projects"])
        return _resource(row)

    async def update_resource(self, resource_id: str, data: ResourceUpdate) -> Resource | None:
        q = select(ResourceRow).where(ResourceRow.id == resource_id).options(selectinload(ResourceRow.projects))
        row = (await self.session.execute(q)).scalar_one_or_none()
        if not row:
            return None
        if data.title is not None:
            row.title = data.title
        if data.description is not None:
            row.description = data.description
        if data.tags is not None:
            row.tags = data.tags
        if data.project_ids is not None:
            proj_q = select(ProjectRow).where(ProjectRow.id.in_(data.project_ids))
            row.projects = (await self.session.execute(proj_q)).scalars().all()
        await self.session.flush()
        return _resource(row)

    # ── Edges ──────────────────────────────────

    async def list_edges(self) -> list[Edge]:
        rows = (await self.session.execute(select(EdgeRow))).scalars().all()
        return [_edge(r) for r in rows]

    async def create_edge(self, data: EdgeCreate) -> Edge:
        row = EdgeRow(
            id=_new_id(),
            from_id=data.from_id,
            to_id=data.to_id,
            relation=data.relation.value,
            note=data.note,
        )
        self.session.add(row)
        await self.session.flush()
        return _edge(row)
