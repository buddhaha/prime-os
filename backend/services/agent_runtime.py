"""
AgentRuntime — executes agents via LiteLLM (Anthropic, Ollama, OpenAI, …).

Design:
  - Each agent run is an asyncio Task.
  - Agents communicate with the LLM using the tool-use / function-calling API.
  - Tools are Python functions exposed as JSON schemas to the model.
  - Results are streamed to the DB log and broadcast over WebSocket.
  - The runtime holds an in-memory registry of agents and active runs.

Model selection:
  Set PRIME_MODEL in .env — LiteLLM routes automatically:
    claude-sonnet-4-6   → Anthropic (requires ANTHROPIC_API_KEY)
    ollama/llama3.1     → local Ollama (no key needed)
    gpt-4o              → OpenAI (requires OPENAI_API_KEY)

Tool inventory:
  list_projects()
  read_project(project_id)
  read_resource(resource_id)
  write_resource(title, type, content, ...)
  create_decision(project_id, title, type, context, body, alternatives)
  create_note(title, content, project_ids, tags)
  link_resources(from_id, to_id, relation)
  web_search(query)
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Callable

import httpx
import litellm

from ..models.agent import (
    Agent, AgentRun, AgentTask, AgentEvent,
    AgentRole, ROLE_PROMPTS,
    LogEntry, LogLevel, RunStatus, AgentTool,
)
from ..models.project import DecisionCreate, DecisionType, Alternative
from ..models.resource import ResourceCreate, ResourceType, EdgeCreate, RelationType
from ..config import settings


# ─────────────────────────────────────────────
# Tool definitions — OpenAI function-calling format (LiteLLM-compatible)
# ─────────────────────────────────────────────

def _fn(name: str, description: str, parameters: dict) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


TOOL_SCHEMAS: list[dict] = [
    _fn("list_projects", "List all PRIME projects with their names, status, and counts.",
        {"type": "object", "properties": {}, "required": []}),

    _fn("read_project", "Get full details for a project: description, decisions, todos, concepts.",
        {"type": "object",
         "properties": {"project_id": {"type": "string", "description": "The project slug ID."}},
         "required": ["project_id"]}),

    _fn("read_resource", "Read the text content of a resource in the knowledge base.",
        {"type": "object",
         "properties": {"resource_id": {"type": "string"}},
         "required": ["resource_id"]}),

    _fn("write_resource", "Save a new resource (article, note, artifact, video summary) to the knowledge base.",
        {"type": "object",
         "properties": {
             "title":       {"type": "string"},
             "type":        {"type": "string", "enum": ["article", "note", "pdf", "video", "artifact"]},
             "content":     {"type": "string", "description": "Markdown content to store."},
             "description": {"type": "string"},
             "project_ids": {"type": "array", "items": {"type": "string"}},
             "tags":        {"type": "array", "items": {"type": "string"}},
         },
         "required": ["title", "type", "content"]}),

    _fn("create_decision", "Record an architectural decision (ADR) in a project.",
        {"type": "object",
         "properties": {
             "project_id":   {"type": "string"},
             "title":        {"type": "string"},
             "type":         {"type": "string", "enum": ["adr", "decision", "milestone", "note"]},
             "context":      {"type": "string"},
             "body":         {"type": "string"},
             "consequences": {"type": "string"},
             "alternatives": {
                 "type": "array",
                 "items": {"type": "object", "properties": {
                     "title":  {"type": "string"},
                     "reason": {"type": "string"},
                 }},
             },
             "tags": {"type": "array", "items": {"type": "string"}},
         },
         "required": ["project_id", "title", "body"]}),

    _fn("create_note", "Create a quick personal note and add it to the knowledge base.",
        {"type": "object",
         "properties": {
             "title":       {"type": "string"},
             "content":     {"type": "string"},
             "project_ids": {"type": "array", "items": {"type": "string"}},
             "tags":        {"type": "array", "items": {"type": "string"}},
         },
         "required": ["title", "content"]}),

    _fn("link_resources", "Add a directed edge between two nodes in the knowledge graph.",
        {"type": "object",
         "properties": {
             "from_id":  {"type": "string"},
             "to_id":    {"type": "string"},
             "relation": {"type": "string", "enum": ["contains", "references", "cites", "related_to", "supersedes"]},
             "note":     {"type": "string"},
         },
         "required": ["from_id", "to_id", "relation"]}),

    _fn("web_search", "Search the web and return a summary of the top results.",
        {"type": "object",
         "properties": {
             "query":       {"type": "string"},
             "max_results": {"type": "integer", "default": 5},
         },
         "required": ["query"]}),
]

def _configure_litellm() -> None:
    """Push provider keys into LiteLLM and suppress its verbose logging."""
    import logging
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    litellm.drop_params = True   # ignore unsupported params per model
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    if settings.ollama_api_base:
        os.environ.setdefault("OLLAMA_API_BASE", settings.ollama_api_base)


# Default agents available without explicit registration
_DEFAULT_AGENTS: list[Agent] = [
    Agent(id="researcher", name="Researcher", role=AgentRole.research,  emoji="🔍"),
    Agent(id="writer",     name="Writer",     role=AgentRole.writer,    emoji="✍️"),
    Agent(id="analyst",    name="Analyst",    role=AgentRole.analyst,   emoji="📊"),
    Agent(id="monitor",    name="Monitor",    role=AgentRole.monitor,   emoji="👁️"),
    Agent(id="coder",      name="Coder",      role=AgentRole.coder,     emoji="💻"),
]


# ─────────────────────────────────────────────
# AgentRuntime
# ─────────────────────────────────────────────

class AgentRuntime:
    """
    Manages concurrent agent execution. Inject via FastAPI dependency.
    """

    def __init__(self, session_factory, graph_engine) -> None:
        self._session_factory = session_factory
        self._graph = graph_engine

        # Agent registry (in-memory; default agents pre-loaded)
        self._agents: dict[str, Agent] = {a.id: a for a in _DEFAULT_AGENTS}

        # run_id → asyncio.Task
        self._active: dict[str, asyncio.Task] = {}
        # run_id → stop event
        self._stop_events: dict[str, asyncio.Event] = {}

        # WebSocket broadcast callback — set by the WS router
        self._broadcast: Callable[[AgentEvent], None] | None = None

        # Wire LiteLLM provider keys from settings so they're available globally
        _configure_litellm()

    # ── Agent registry ──────────────────────────

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def register_agent(self, agent: Agent) -> Agent:
        self._agents[agent.id] = agent
        return agent

    def set_broadcaster(self, fn: Callable[[AgentEvent], None]) -> None:
        self._broadcast = fn

    @asynccontextmanager
    async def _store(self):
        """Short-lived DB session for a single operation or transaction."""
        from .db_store import DBStore
        async with self._session_factory() as session:
            async with session.begin():
                yield DBStore(session)

    # ── Public API ──────────────────────────────

    async def start_run(self, agent: Agent, task: AgentTask) -> AgentRun:
        run_id = str(uuid.uuid4())[:12]
        run = AgentRun(
            id=run_id,
            agent_id=agent.id,
            agent_name=agent.name,
            task_id=task.id,
            task=task.task,
            project_id=task.project_id,
            status=RunStatus.running,
            started=datetime.utcnow(),
        )
        async with self._store() as store:
            await store.create_run(run)

        stop_event = asyncio.Event()
        self._stop_events[run_id] = stop_event

        coro = self._execute(agent, task, run, stop_event)
        t = asyncio.create_task(coro, name=f"run-{run_id}")
        self._active[run_id] = t
        t.add_done_callback(lambda _: self._active.pop(run_id, None))

        await self._emit(AgentEvent(event="run_started", run_id=run_id, payload=run.model_dump()))
        return run

    async def stop_run(self, run_id: str) -> bool:
        if run_id in self._stop_events:
            self._stop_events[run_id].set()
            return True
        return False

    async def pause_run(self, run_id: str) -> bool:
        return await self.stop_run(run_id)

    # ── Execution loop ──────────────────────────

    async def _execute(
        self,
        agent: Agent,
        task: AgentTask,
        run: AgentRun,
        stop: asyncio.Event,
    ) -> None:
        import logging
        log = logging.getLogger("prime.agent")

        await self._log(run.id, LogLevel.info, f"Starting task: {task.task}")

        allowed = {t.value for t in agent.tools} if agent.tools else {s["function"]["name"] for s in TOOL_SCHEMAS}
        tools = [s for s in TOOL_SCHEMAS if s["function"]["name"] in allowed]

        user_msg = task.task
        if task.context:
            user_msg = f"{task.task}\n\nContext:\n{task.context}"
        if task.project_id:
            user_msg += f"\n\nProject context ID: {task.project_id}"

        # LiteLLM uses OpenAI message format — system goes in messages list
        messages: list[dict] = [
            {"role": "system",  "content": agent.effective_system_prompt()},
            {"role": "user",    "content": user_msg},
        ]
        model = agent.model or settings.prime_model

        turns = 0
        final_text = ""

        try:
            while turns < agent.max_turns and not stop.is_set():
                turns += 1
                await self._log(run.id, LogLevel.info, f"Turn {turns}/{agent.max_turns}")
                async with self._store() as store:
                    await store.update_run(run.id, {
                        "turns": turns,
                        "progress": min(95, turns * (90 // agent.max_turns)),
                    })

                response = await litellm.acompletion(
                    model=model,
                    max_tokens=agent.max_tokens,
                    tools=tools,
                    messages=messages,
                )

                msg = response.choices[0].message
                turn_text   = msg.content or ""
                tool_calls  = msg.tool_calls or []
                finish      = response.choices[0].finish_reason

                if turn_text:
                    final_text += turn_text + "\n"
                    await self._log(run.id, LogLevel.info,
                                    turn_text[:200] + ("…" if len(turn_text) > 200 else ""))

                # Append assistant turn in OpenAI format
                messages.append({"role": "assistant", "content": turn_text,
                                  "tool_calls": [tc.model_dump() for tc in tool_calls] or None})

                if finish == "stop" and not tool_calls:
                    await self._log(run.id, LogLevel.ok, "Agent finished.")
                    break

                if tool_calls:
                    for call in tool_calls:
                        fn_name = call.function.name
                        fn_args = json.loads(call.function.arguments or "{}")
                        result  = await self._dispatch_tool(run, agent, fn_name, fn_args)
                        messages.append({
                            "role":         "tool",
                            "tool_call_id": call.id,
                            "content":      json.dumps(result),
                        })

            # Save final text as a knowledge base note
            if final_text.strip():
                async with self._store() as store:
                    rc = ResourceCreate(
                        type=ResourceType.note,
                        title=f"Agent result: {task.task[:60]}",
                        description=f"Generated by {agent.name} agent, run {run.id}",
                        project_ids=[task.project_id] if task.project_id else [],
                        tags=["agent-output", agent.role.value],
                        content=final_text.strip(),
                    )
                    resource = await store.create_resource(rc)
                    self._graph.add_resource(resource)

            async with self._store() as store:
                await store.update_run(run.id, {
                    "status": RunStatus.completed,
                    "progress": 100,
                    "finished": datetime.utcnow(),
                })
            await self._log(run.id, LogLevel.ok, "Run completed successfully.")
            await self._emit(AgentEvent(event="run_done", run_id=run.id, payload={"progress": 100}))

        except asyncio.CancelledError:
            async with self._store() as store:
                await store.update_run(run.id, {
                    "status": RunStatus.cancelled,
                    "finished": datetime.utcnow(),
                })
            await self._log(run.id, LogLevel.warn, "Run cancelled.")

        except Exception as exc:
            msg = str(exc)
            log.exception(f"Agent run {run.id} failed")
            async with self._store() as store:
                await store.update_run(run.id, {
                    "status": RunStatus.error,
                    "error_msg": msg,
                    "finished": datetime.utcnow(),
                })
            await self._log(run.id, LogLevel.error, f"Run failed: {msg}")
            await self._emit(AgentEvent(event="run_error", run_id=run.id, payload={"error": msg}))

        finally:
            self._stop_events.pop(run.id, None)

    # ── Tool dispatcher ─────────────────────────

    async def _dispatch_tool(self, run: AgentRun, agent: Agent, name: str, args: dict) -> Any:
        await self._log(run.id, LogLevel.tool, f"→ {name}({json.dumps(args)[:120]})")
        await self._emit(AgentEvent(
            event="tool_call", run_id=run.id,
            payload={"tool": name, "input": args},
        ))
        try:
            result = await self._call_tool(run, agent, name, args)
            await self._log(run.id, LogLevel.ok, f"← {name}: {str(result)[:120]}")
            return result
        except Exception as e:
            await self._log(run.id, LogLevel.error, f"← {name} error: {e}")
            return {"error": str(e)}

    async def _call_tool(self, run: AgentRun, agent: Agent, name: str, args: dict) -> Any:
        if name == "list_projects":
            async with self._store() as store:
                projects = await store.list_projects()
            return [{"id": p.id, "name": p.name, "status": p.status,
                     "description": p.description} for p in projects]

        elif name == "read_project":
            async with self._store() as store:
                detail = await store.get_project_detail(args["project_id"])
            if not detail:
                return {"error": "Project not found"}
            return detail.model_dump()

        elif name == "read_resource":
            async with self._store() as store:
                content = await store.read_resource_content(args["resource_id"])
                if content is None:
                    res = await store.get_resource(args["resource_id"])
                    return ({"error": "No content"} if not res
                            else {"title": res.title, "description": res.description})
            return {"content": content}

        elif name == "write_resource":
            async with self._store() as store:
                rc = ResourceCreate(
                    type=ResourceType(args["type"]),
                    title=args["title"],
                    content=args.get("content", ""),
                    description=args.get("description", ""),
                    project_ids=args.get("project_ids") or (
                        [run.project_id] if run.project_id else []
                    ),
                    tags=args.get("tags", []),
                )
                resource = await store.create_resource(rc)
            self._graph.add_resource(resource)
            return {"id": resource.id, "title": resource.title}

        elif name == "create_decision":
            alts = [
                Alternative(title=a["title"], reason=a.get("reason", ""))
                for a in args.get("alternatives", [])
            ]
            async with self._store() as store:
                dc = DecisionCreate(
                    project_id=args["project_id"],
                    title=args["title"],
                    type=DecisionType(args.get("type", "decision")),
                    context=args.get("context", ""),
                    body=args["body"],
                    consequences=args.get("consequences", ""),
                    alternatives=alts,
                    tags=args.get("tags", []),
                )
                decision = await store.create_decision(dc)
            return {"id": decision.id, "title": decision.title}

        elif name == "create_note":
            async with self._store() as store:
                rc = ResourceCreate(
                    type=ResourceType.note,
                    title=args["title"],
                    content=args.get("content", ""),
                    project_ids=args.get("project_ids", []),
                    tags=args.get("tags", []),
                )
                resource = await store.create_resource(rc)
            self._graph.add_resource(resource)
            return {"id": resource.id, "title": resource.title}

        elif name == "link_resources":
            async with self._store() as store:
                ec = EdgeCreate(
                    from_id=args["from_id"],
                    to_id=args["to_id"],
                    relation=RelationType(args["relation"]),
                    note=args.get("note", ""),
                )
                edge = await store.create_edge(ec)
            self._graph.add_edge(edge)
            return {"edge_id": edge.id}

        elif name == "web_search":
            return await self._web_search(args["query"], args.get("max_results", 5))

        return {"error": f"Unknown tool: {name}"}

    async def _web_search(self, query: str, max_results: int = 5) -> dict:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_redirect": 1, "no_html": 1}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            data = resp.json()

        results = []
        abstract = data.get("AbstractText", "")
        if abstract:
            results.append({
                "title": data.get("Heading", query),
                "snippet": abstract,
                "url": data.get("AbstractURL", ""),
            })
        for item in data.get("RelatedTopics", [])[:max_results]:
            if "Text" in item:
                results.append({
                    "title": item.get("Text", "")[:80],
                    "snippet": item.get("Text", ""),
                    "url": item.get("FirstURL", ""),
                })
        return {"query": query, "results": results[:max_results]}

    # ── Helpers ─────────────────────────────────

    async def _log(self, run_id: str, level: LogLevel, message: str) -> None:
        entry = LogEntry(level=level, message=message)
        async with self._store() as store:
            await store.append_log(run_id, entry)
        await self._emit(AgentEvent(
            event="log",
            run_id=run_id,
            payload=entry.model_dump(),
        ))

    async def _emit(self, event: AgentEvent) -> None:
        if self._broadcast:
            try:
                self._broadcast(event)
            except Exception:
                pass
