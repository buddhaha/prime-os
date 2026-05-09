"""
FileStore — all read/write operations on the ~/PRIME workspace.

Everything is stored as plain files so it's human-readable, git-trackable,
and survives any database migration. No SQLite, no Postgres — just the
filesystem as the single source of truth.

Directory layout:
  {root}/
    projects/
      {project_id}/
        project.json
        decisions/
          {id}-{slug}.md      ← YAML frontmatter + Markdown body
        todos.json
        concepts.json
    knowledge/
      nodes.json              ← list[Resource]
      edges.json              ← list[Edge]
      articles/
      notes/
      pdfs/
      videos/
      artifacts/
    agents/
      registry.json           ← list[Agent]
      queue.json              ← list[AgentTask]
      runs/
        {run_id}/
          run.json
          log.jsonl
          result.md
    config.json
"""

import json
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml  # PyYAML

from ..models.project import (
    Project, ProjectCreate, ProjectStatus,
    Decision, DecisionCreate, DecisionType, DecisionStatus, Alternative,
    Todo, TodoCreate, TodoUpdate, TodoStatus, Priority,
    Concept, ProjectDetail,
)
from ..models.resource import Resource, ResourceCreate, ResourceUpdate, Edge, EdgeCreate
from ..models.agent import Agent, AgentCreate, AgentTask, AgentTaskCreate, AgentRun, RunStatus, LogEntry
from ..config import settings


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())[:8]


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:48]


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from Markdown body."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return fm, body


def _render_frontmatter(fm: dict, body: str) -> str:
    return f"---\n{yaml.dump(fm, allow_unicode=True)}---\n\n{body}"


# ─────────────────────────────────────────────
# FileStore class
# ─────────────────────────────────────────────

class FileStore:
    """
    Thin filesystem abstraction. All methods are synchronous; wrap with
    asyncio.to_thread() at the API layer for non-blocking I/O.
    """

    def __init__(self, root: Path | None = None):
        self.root = root or settings.workspace_path
        self._ensure_structure()

    def _ensure_structure(self) -> None:
        """Create the workspace directory skeleton on first run."""
        for sub in [
            "projects",
            "knowledge/articles",
            "knowledge/notes",
            "knowledge/pdfs",
            "knowledge/videos",
            "knowledge/artifacts",
            "agents/runs",
        ]:
            (self.root / sub).mkdir(parents=True, exist_ok=True)

        # Seed empty indexes if missing
        for path, default in [
            (self.root / "knowledge" / "nodes.json", []),
            (self.root / "knowledge" / "edges.json", []),
            (self.root / "agents" / "registry.json", []),
            (self.root / "agents" / "queue.json", []),
        ]:
            if not path.exists():
                _write_json(path, default)

    # ─────────────────────────────────────────
    # Projects
    # ─────────────────────────────────────────

    def list_projects(self) -> list[Project]:
        projects = []
        for p in sorted((self.root / "projects").iterdir()):
            if p.is_dir():
                proj = self._load_project(p)
                if proj:
                    projects.append(proj)
        return projects

    def get_project(self, project_id: str) -> Project | None:
        path = self.root / "projects" / project_id
        return self._load_project(path)

    def get_project_detail(self, project_id: str) -> ProjectDetail | None:
        project = self.get_project(project_id)
        if not project:
            return None
        return ProjectDetail(
            project=project,
            decisions=self.list_decisions(project_id),
            todos=self.list_todos(project_id),
            concepts=self.list_concepts(project_id),
        )

    def create_project(self, data: ProjectCreate) -> Project:
        project_id = _slugify(data.name)
        path = self.root / "projects" / project_id
        if path.exists():
            project_id = f"{project_id}-{_new_id()}"
            path = self.root / "projects" / project_id

        project = Project(id=project_id, **data.model_dump())
        path.mkdir(parents=True, exist_ok=True)
        (path / "decisions").mkdir(exist_ok=True)
        _write_json(path / "project.json", project.model_dump())
        _write_json(path / "todos.json", [])
        _write_json(path / "concepts.json", [])
        return project

    def update_project(self, project_id: str, updates: dict) -> Project | None:
        path = self.root / "projects" / project_id / "project.json"
        if not path.exists():
            return None
        data = _read_json(path)
        data.update(updates)
        data["updated"] = str(date.today())
        _write_json(path, data)
        return Project(**data)

    def _load_project(self, path: Path) -> Project | None:
        meta_file = path / "project.json"
        if not meta_file.exists():
            return None
        data = _read_json(meta_file)
        project = Project(**data)

        # Enrich with counts
        project.decision_count = len(list((path / "decisions").glob("*.md")))
        todos = _read_json(path / "todos.json") or []
        project.todo_count = sum(1 for t in todos if t.get("status") == "open")
        done = sum(1 for t in todos if t.get("status") == "done")
        total = len(todos)
        project.progress = int((done / total) * 100) if total else 0

        # Resource count: edges pointing to this project
        edges = _read_json(self.root / "knowledge" / "edges.json") or []
        project.resource_count = sum(
            1 for e in edges if e.get("from_id") == project.id
        )
        return project

    # ─────────────────────────────────────────
    # Decisions / ADRs
    # ─────────────────────────────────────────

    def list_decisions(self, project_id: str) -> list[Decision]:
        dec_dir = self.root / "projects" / project_id / "decisions"
        if not dec_dir.exists():
            return []
        decisions = []
        for f in sorted(dec_dir.glob("*.md")):
            d = self._load_decision(project_id, f)
            if d:
                decisions.append(d)
        return decisions

    def get_decision(self, project_id: str, decision_id: str) -> Decision | None:
        dec_dir = self.root / "projects" / project_id / "decisions"
        for f in dec_dir.glob(f"{decision_id}-*.md"):
            return self._load_decision(project_id, f)
        return None

    def create_decision(self, data: DecisionCreate) -> Decision:
        # Auto-number: ADR-001, ADR-002, …
        dec_dir = self.root / "projects" / data.project_id / "decisions"
        dec_dir.mkdir(parents=True, exist_ok=True)
        existing = list(dec_dir.glob("*.md"))
        n = len(existing) + 1
        decision_id = f"ADR-{n:03d}"

        decision = Decision(
            id=decision_id,
            project_id=data.project_id,
            title=data.title,
            type=data.type,
            context=data.context,
            body=data.body,
            consequences=data.consequences,
            alternatives=data.alternatives,
            tags=data.tags,
        )

        fm = {
            "id": decision.id,
            "project": decision.project_id,
            "title": decision.title,
            "date": str(decision.date),
            "type": decision.type.value,
            "status": decision.status.value,
            "tags": decision.tags,
            "alternatives": [
                {"title": a.title, "reason": a.reason}
                for a in decision.alternatives
            ],
        }
        sections = []
        if decision.context:
            sections.append(f"## Context\n\n{decision.context}")
        if decision.body:
            sections.append(f"## Decision\n\n{decision.body}")
        if decision.consequences:
            sections.append(f"## Consequences\n\n{decision.consequences}")

        body = "\n\n".join(sections)
        content = _render_frontmatter(fm, body)
        (dec_dir / f"{decision.slug}.md").write_text(content, encoding="utf-8")
        return decision

    def _load_decision(self, project_id: str, path: Path) -> Decision | None:
        text = path.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(text)
        if not fm:
            return None

        # Parse ## sections from body
        sections: dict[str, str] = {}
        current = None
        lines: list[str] = []
        for line in body.splitlines():
            if line.startswith("## "):
                if current:
                    sections[current] = "\n".join(lines).strip()
                current = line[3:].strip()
                lines = []
            else:
                lines.append(line)
        if current:
            sections[current] = "\n".join(lines).strip()

        alts = [
            Alternative(title=a["title"], reason=a.get("reason", ""))
            for a in (fm.get("alternatives") or [])
        ]

        return Decision(
            id=fm.get("id", path.stem),
            project_id=project_id,
            title=fm.get("title", path.stem),
            date=fm.get("date", date.today()),
            type=DecisionType(fm.get("type", "decision")),
            status=DecisionStatus(fm.get("status", "accepted")),
            context=sections.get("Context", ""),
            body=sections.get("Decision", ""),
            consequences=sections.get("Consequences", ""),
            alternatives=alts,
            tags=fm.get("tags") or [],
        )

    # ─────────────────────────────────────────
    # Todos
    # ─────────────────────────────────────────

    def list_todos(self, project_id: str) -> list[Todo]:
        data = _read_json(self.root / "projects" / project_id / "todos.json") or []
        return [Todo(**t) for t in data]

    def create_todo(self, project_id: str, data: TodoCreate) -> Todo:
        todos_path = self.root / "projects" / project_id / "todos.json"
        todos = _read_json(todos_path) or []
        todo = Todo(id=_new_id(), project_id=project_id, **data.model_dump())
        todos.append(todo.model_dump())
        _write_json(todos_path, todos)
        return todo

    def update_todo(self, project_id: str, todo_id: str, data: TodoUpdate) -> Todo | None:
        todos_path = self.root / "projects" / project_id / "todos.json"
        todos = _read_json(todos_path) or []
        for t in todos:
            if t["id"] == todo_id:
                updates = {k: v for k, v in data.model_dump().items() if v is not None}
                t.update(updates)
                if updates.get("status") == "done":
                    t["completed"] = str(date.today())
                _write_json(todos_path, todos)
                return Todo(**t)
        return None

    # ─────────────────────────────────────────
    # Concepts
    # ─────────────────────────────────────────

    def list_concepts(self, project_id: str) -> list[Concept]:
        data = _read_json(self.root / "projects" / project_id / "concepts.json") or []
        return [Concept(**c) for c in data]

    def create_concept(self, project_id: str, name: str, desc: str = "") -> Concept:
        path = self.root / "projects" / project_id / "concepts.json"
        concepts = _read_json(path) or []
        concept = Concept(id=_new_id(), name=name, desc=desc)
        concepts.append(concept.model_dump())
        _write_json(path, concepts)
        return concept

    # ─────────────────────────────────────────
    # Resources (knowledge base)
    # ─────────────────────────────────────────

    def list_resources(self, type_filter: str | None = None, project_id: str | None = None) -> list[Resource]:
        data = _read_json(self.root / "knowledge" / "nodes.json") or []
        resources = [Resource(**r) for r in data]
        if type_filter:
            resources = [r for r in resources if r.type.value == type_filter]
        if project_id:
            resources = [r for r in resources if project_id in r.project_ids]
        return resources

    def get_resource(self, resource_id: str) -> Resource | None:
        for r in self.list_resources():
            if r.id == resource_id:
                return r
        return None

    def create_resource(self, data: ResourceCreate) -> Resource:
        nodes_path = self.root / "knowledge" / "nodes.json"
        nodes = _read_json(nodes_path) or []

        resource_id = _new_id()
        subdir = self.root / "knowledge" / f"{data.type.value}s"
        subdir.mkdir(parents=True, exist_ok=True)

        # Determine file path for content storage
        filename = _slugify(data.title)
        if data.type.value in ("article", "note", "video"):
            content_path = subdir / f"{filename}.md"
            if data.content:
                content_path.write_text(data.content, encoding="utf-8")
            rel_path = str(content_path.relative_to(self.root))
        elif data.type.value == "artifact":
            rel_path = None  # artifact path provided externally
        else:
            rel_path = None  # pdf uploaded separately

        resource = Resource(
            id=resource_id,
            type=data.type,
            title=data.title,
            description=data.description,
            path=rel_path,
            source_url=data.source_url,
            project_ids=data.project_ids,
            tags=data.tags,
        )
        nodes.append(resource.model_dump())
        _write_json(nodes_path, nodes)

        # Auto-create edges for each project association
        for pid in data.project_ids:
            self.create_edge(EdgeCreate(from_id=pid, to_id=resource_id, relation="contains"))

        return resource

    def update_resource(self, resource_id: str, data: ResourceUpdate) -> Resource | None:
        nodes_path = self.root / "knowledge" / "nodes.json"
        nodes = _read_json(nodes_path) or []
        for n in nodes:
            if n["id"] == resource_id:
                updates = {k: v for k, v in data.model_dump().items() if v is not None}
                n.update(updates)
                n["updated"] = str(datetime.utcnow())
                _write_json(nodes_path, nodes)
                return Resource(**n)
        return None

    def read_resource_content(self, resource_id: str) -> str | None:
        resource = self.get_resource(resource_id)
        if not resource or not resource.path:
            return None
        path = self.root / resource.path
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write_resource_content(self, resource_id: str, content: str) -> bool:
        resource = self.get_resource(resource_id)
        if not resource:
            return False
        if not resource.path:
            # Create a path for it
            subdir = self.root / "knowledge" / f"{resource.type.value}s"
            subdir.mkdir(parents=True, exist_ok=True)
            path = subdir / f"{_slugify(resource.title)}.md"
            self.update_resource(resource_id, ResourceUpdate())
        else:
            path = self.root / resource.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True

    # ─────────────────────────────────────────
    # Edges (knowledge graph links)
    # ─────────────────────────────────────────

    def list_edges(self) -> list[Edge]:
        data = _read_json(self.root / "knowledge" / "edges.json") or []
        return [Edge(**e) for e in data]

    def create_edge(self, data: EdgeCreate) -> Edge:
        edges_path = self.root / "knowledge" / "edges.json"
        edges = _read_json(edges_path) or []
        # Deduplicate
        for e in edges:
            if e["from_id"] == data.from_id and e["to_id"] == data.to_id and e["relation"] == data.relation:
                return Edge(**e)
        edge = Edge(id=_new_id(), **data.model_dump())
        edges.append(edge.model_dump())
        _write_json(edges_path, edges)
        return edge

    def delete_edge(self, edge_id: str) -> bool:
        edges_path = self.root / "knowledge" / "edges.json"
        edges = _read_json(edges_path) or []
        new_edges = [e for e in edges if e["id"] != edge_id]
        if len(new_edges) == len(edges):
            return False
        _write_json(edges_path, new_edges)
        return True

    # ─────────────────────────────────────────
    # Agents
    # ─────────────────────────────────────────

    def list_agents(self) -> list[Agent]:
        data = _read_json(self.root / "agents" / "registry.json") or []
        return [Agent(**a) for a in data]

    def get_agent(self, agent_id: str) -> Agent | None:
        for a in self.list_agents():
            if a.id == agent_id:
                return a
        return None

    def create_agent(self, data: AgentCreate) -> Agent:
        reg_path = self.root / "agents" / "registry.json"
        registry = _read_json(reg_path) or []
        agent = Agent(id=_new_id(), **data.model_dump())
        registry.append(agent.model_dump())
        _write_json(reg_path, registry)
        return agent

    # ─────────────────────────────────────────
    # Task queue
    # ─────────────────────────────────────────

    def list_queue(self) -> list[AgentTask]:
        data = _read_json(self.root / "agents" / "queue.json") or []
        return [AgentTask(**t) for t in data]

    def enqueue_task(self, data: AgentTaskCreate) -> AgentTask:
        queue_path = self.root / "agents" / "queue.json"
        queue = _read_json(queue_path) or []
        task = AgentTask(id=_new_id(), **data.model_dump())
        queue.append(task.model_dump())
        # Sort by priority
        queue.sort(key=lambda t: t.get("priority", 5))
        _write_json(queue_path, queue)
        return task

    def dequeue_task(self, task_id: str) -> bool:
        """Remove a task from the queue (called when the agent picks it up)."""
        queue_path = self.root / "agents" / "queue.json"
        queue = _read_json(queue_path) or []
        new_queue = [t for t in queue if t["id"] != task_id]
        _write_json(queue_path, new_queue)
        return len(new_queue) < len(queue)

    # ─────────────────────────────────────────
    # Agent runs
    # ─────────────────────────────────────────

    def create_run(self, run: AgentRun) -> AgentRun:
        run_dir = self.root / "agents" / "runs" / run.id
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(run_dir / "run.json", run.model_dump())
        return run

    def get_run(self, run_id: str) -> AgentRun | None:
        run_file = self.root / "agents" / "runs" / run_id / "run.json"
        if not run_file.exists():
            return None
        data = _read_json(run_file)
        run = AgentRun(**data)
        # Attach recent log entries
        run.log = self.read_run_log(run_id)[-20:]
        return run

    def update_run(self, run_id: str, updates: dict) -> None:
        run_file = self.root / "agents" / "runs" / run_id / "run.json"
        if not run_file.exists():
            return
        data = _read_json(run_file)
        data.update(updates)
        _write_json(run_file, data)

    def list_runs(self, agent_id: str | None = None, status: str | None = None) -> list[AgentRun]:
        runs_dir = self.root / "agents" / "runs"
        runs = []
        for run_dir in sorted(runs_dir.iterdir(), reverse=True):
            if run_dir.is_dir():
                run = self.get_run(run_dir.name)
                if run:
                    if agent_id and run.agent_id != agent_id:
                        continue
                    if status and run.status.value != status:
                        continue
                    runs.append(run)
        return runs

    def append_log(self, run_id: str, entry: LogEntry) -> None:
        log_path = self.root / "agents" / "runs" / run_id / "log.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    def read_run_log(self, run_id: str) -> list[LogEntry]:
        log_path = self.root / "agents" / "runs" / run_id / "log.jsonl"
        if not log_path.exists():
            return []
        entries = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(LogEntry.model_validate_json(line))
            except Exception:
                pass
        return entries

    def write_run_result(self, run_id: str, content: str) -> str:
        result_path = self.root / "agents" / "runs" / run_id / "result.md"
        result_path.write_text(content, encoding="utf-8")
        return str(result_path)

    def read_run_result(self, run_id: str) -> str | None:
        result_path = self.root / "agents" / "runs" / run_id / "result.md"
        return result_path.read_text(encoding="utf-8") if result_path.exists() else None
