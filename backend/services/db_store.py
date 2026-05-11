"""
PRIME OS — PostgreSQL-backed store (replaces file_store.py).
"""

from __future__ import annotations

from datetime import date
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import (
    ProjectRow, DecisionRow, TodoRow, ConceptRow, ResourceRow, EdgeRow,
    ProposalRow, AgentRunRow, AgentLogRow, resource_projects,
)
from ..models.project import (
    Project, ProjectCreate, ProjectDetail,
    Decision, DecisionCreate,
    Todo, TodoCreate, TodoUpdate,
    Concept, ConceptCreate,
)
from ..models.resource import (
    Resource, ResourceCreate, ResourceUpdate, ResourceStatus,
    Edge, EdgeCreate,
    Proposal, ProposalCreate, ProposalStatus,
)
from ..models.agent import AgentRun, RunStatus, LogEntry, LogLevel


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
        status=row.status or "inbox",
        origin=row.origin or "manual",
    )


def _edge(row: EdgeRow) -> Edge:
    return Edge(
        id=row.id, from_id=row.from_id, to_id=row.to_id,
        relation=row.relation, note=row.note or "",
    )


def _proposal(row: ProposalRow) -> Proposal:
    return Proposal(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        resource_type=row.resource_type,
        source_url=row.source_url,
        read_time=row.read_time,
        why_relevant=row.why_relevant or "",
        takeaways=row.takeaways or [],
        gap_type=row.gap_type or "",
        gap_label=row.gap_label or "",
        status=row.status or "pending",
        created=row.created,
    )


def _run(row: AgentRunRow) -> AgentRun:
    return AgentRun(
        id=row.id,
        agent_id=row.agent_id,
        agent_name=row.agent_name or "",
        task_id="",
        task=row.task,
        project_id=row.project_id,
        status=RunStatus(row.status),
        progress=row.progress or 0,
        turns=row.turns or 0,
        started=row.started,
        finished=row.finished,
        error_msg=row.error_msg or "",
    )


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
        allowed = {"name", "emoji", "description", "color", "status", "project_type", "tags", "progress"}
        for k, v in updates.items():
            if k in allowed:
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
            date=date.today(),
            type=data.type.value,
            status="accepted",
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
            proj.updated = date.today()

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
            status=data.status.value,
            origin=data.origin.value,
        )
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
        if data.content is not None:
            row.content = data.content
        if data.status is not None:
            row.status = data.status.value
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

    async def delete_edge(self, edge_id: str) -> bool:
        row = (await self.session.execute(select(EdgeRow).where(EdgeRow.id == edge_id))).scalar_one_or_none()
        if not row:
            return False
        await self.session.delete(row)
        return True

    # ── Proposals ──────────────────────────────

    async def list_proposals(self, project_id: str | None = None, status: str | None = None) -> list[Proposal]:
        q = select(ProposalRow).order_by(ProposalRow.created.desc())
        if project_id:
            q = q.where(ProposalRow.project_id == project_id)
        if status:
            q = q.where(ProposalRow.status == status)
        rows = (await self.session.execute(q)).scalars().all()
        return [_proposal(r) for r in rows]

    async def create_proposal(self, data: ProposalCreate) -> Proposal:
        row = ProposalRow(
            id=_new_id(),
            project_id=data.project_id,
            title=data.title,
            resource_type=data.resource_type.value,
            source_url=data.source_url,
            read_time=data.read_time,
            why_relevant=data.why_relevant,
            takeaways=data.takeaways,
            gap_type=data.gap_type,
            gap_label=data.gap_label,
            status="pending",
            created=date.today(),
        )
        self.session.add(row)
        await self.session.flush()
        return _proposal(row)

    async def accept_proposal(self, proposal_id: str) -> Resource | None:
        """Accept a proposal — creates a Resource (origin=suggested) and marks proposal accepted."""
        q = select(ProposalRow).where(ProposalRow.id == proposal_id)
        row = (await self.session.execute(q)).scalar_one_or_none()
        if not row or row.status != "pending":
            return None

        import json as _json
        # Create the resource — store why_relevant in description, takeaways as JSON in content
        resource = await self.create_resource(ResourceCreate(
            type=row.resource_type,
            title=row.title,
            description=row.why_relevant,
            source_url=row.source_url,
            project_ids=[row.project_id],
            tags=[row.gap_type, row.gap_label] if row.gap_label else [],
            status=ResourceStatus.inbox,
            origin="suggested",
            content=_json.dumps(row.takeaways or []),
        ))

        # Mark proposal accepted
        row.status = "accepted"
        await self.session.flush()
        return resource

    async def dismiss_proposal(self, proposal_id: str) -> bool:
        q = select(ProposalRow).where(ProposalRow.id == proposal_id)
        row = (await self.session.execute(q)).scalar_one_or_none()
        if not row:
            return False
        row.status = "dismissed"
        await self.session.flush()
        return True

    # ── Agent runs ─────────────────────────────

    async def create_run(self, run: AgentRun) -> AgentRun:
        row = AgentRunRow(
            id=run.id,
            agent_id=run.agent_id,
            agent_name=getattr(run, "agent_name", ""),
            task=run.task,
            project_id=run.project_id,
            status=run.status.value,
            progress=run.progress,
            turns=run.turns,
            started=run.started,
            finished=run.finished,
            error_msg=run.error_msg,
        )
        self.session.add(row)
        await self.session.flush()
        return run

    async def update_run(self, run_id: str, updates: dict) -> None:
        row = (await self.session.execute(
            select(AgentRunRow).where(AgentRunRow.id == run_id)
        )).scalar_one_or_none()
        if not row:
            return
        for key, val in updates.items():
            setattr(row, key, val.value if isinstance(val, RunStatus) else val)
        await self.session.flush()

    async def get_run(self, run_id: str) -> AgentRun | None:
        row = (await self.session.execute(
            select(AgentRunRow).where(AgentRunRow.id == run_id)
        )).scalar_one_or_none()
        return _run(row) if row else None

    async def list_runs(self, agent_id: str | None = None, status: str | None = None) -> list[AgentRun]:
        q = select(AgentRunRow).order_by(AgentRunRow.started.desc())
        if agent_id:
            q = q.where(AgentRunRow.agent_id == agent_id)
        if status:
            q = q.where(AgentRunRow.status == status)
        rows = (await self.session.execute(q)).scalars().all()
        return [_run(r) for r in rows]

    async def append_log(self, run_id: str, entry: LogEntry) -> None:
        row = AgentLogRow(
            id=_new_id(),
            run_id=run_id,
            ts=entry.ts,
            level=entry.level.value,
            message=entry.message,
        )
        self.session.add(row)
        await self.session.flush()

    async def get_run_logs(self, run_id: str) -> list[LogEntry]:
        rows = (await self.session.execute(
            select(AgentLogRow).where(AgentLogRow.run_id == run_id).order_by(AgentLogRow.ts)
        )).scalars().all()
        return [LogEntry(ts=r.ts, level=LogLevel(r.level), message=r.message) for r in rows]

    # ── Resource helpers for agents ─────────────

    async def get_resource(self, resource_id: str) -> Resource | None:
        row = (await self.session.execute(
            select(ResourceRow).where(ResourceRow.id == resource_id)
        )).scalar_one_or_none()
        return _resource(row) if row else None

    async def read_resource_content(self, resource_id: str) -> str | None:
        row = (await self.session.execute(
            select(ResourceRow).where(ResourceRow.id == resource_id)
        )).scalar_one_or_none()
        return row.content if row and row.content else None
