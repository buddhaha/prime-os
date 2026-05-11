"""
AgentRuntime — executes agents using the Anthropic Claude API.

Design:
  - Each agent run is an asyncio Task.
  - Agents communicate with Claude using the tool-use API.
  - Tools are Python functions exposed as JSON schemas to Claude.
  - Results are streamed to JSONL logs and broadcast over WebSocket.
  - The runtime holds a registry of active runs so they can be paused/stopped.

Tool inventory (what agents can do):
  read_resource(id)              — read a resource's content from the workspace
  write_resource(title, type, content, project_ids)  — save a new resource
  create_decision(project_id, title, type, context, body, alternatives)
  create_note(title, content, project_ids, tags)
  link_resources(from_id, to_id, relation)
  list_projects()
  read_project(project_id)       — get project details + decisions + todos
  web_search(query)              — lightweight web search via DuckDuckGo
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Callable, AsyncIterator

import httpx

from . import llm
from ..models.agent import (
    Agent, AgentRun, AgentTask, AgentEvent,
    LogEntry, LogLevel, RunStatus, AgentTool,
)
from ..models.project import DecisionCreate, DecisionType, Alternative
from ..models.resource import ResourceCreate, ResourceType, EdgeCreate, RelationType


# ─────────────────────────────────────────────
# Tool definitions (JSON schema for Claude)
# ─────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "list_projects",
        "description": "List all PRIME projects with their names, status, and counts.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_project",
        "description": "Get full details for a project: description, decisions, todos, concepts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "The project slug ID."},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "read_resource",
        "description": "Read the text content of a resource in the knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_id": {"type": "string"},
            },
            "required": ["resource_id"],
        },
    },
    {
        "name": "write_resource",
        "description": "Save a new resource (article, note, artifact, video summary) to the knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string"},
                "type":        {"type": "string", "enum": ["article", "note", "pdf", "video", "artifact"]},
                "content":     {"type": "string", "description": "Markdown content to store."},
                "description": {"type": "string"},
                "project_ids": {"type": "array", "items": {"type": "string"}},
                "tags":        {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "type", "content"],
        },
    },
    {
        "name": "create_decision",
        "description": "Record an architectural decision (ADR) in a project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id":   {"type": "string"},
                "title":        {"type": "string"},
                "type":         {"type": "string", "enum": ["adr", "decision", "milestone", "note"]},
                "context":      {"type": "string", "description": "Why this decision was needed."},
                "body":         {"type": "string", "description": "What was decided."},
                "consequences": {"type": "string"},
                "alternatives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title":  {"type": "string"},
                            "reason": {"type": "string"},
                        },
                    },
                },
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["project_id", "title", "body"],
        },
    },
    {
        "name": "create_note",
        "description": "Create a quick personal note and add it to the knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string"},
                "content":     {"type": "string"},
                "project_ids": {"type": "array", "items": {"type": "string"}},
                "tags":        {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "link_resources",
        "description": "Add a directed edge between two nodes in the knowledge graph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_id":  {"type": "string"},
                "to_id":    {"type": "string"},
                "relation": {
                    "type": "string",
                    "enum": ["contains", "references", "cites", "related_to", "supersedes"],
                },
                "note": {"type": "string"},
            },
            "required": ["from_id", "to_id", "relation"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web and return a summary of the top results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
]


# ─────────────────────────────────────────────
# AgentRuntime
# ─────────────────────────────────────────────

class AgentRuntime:
    """
    Manages concurrent agent execution. Inject via FastAPI dependency.
    """

    def __init__(self, file_store, graph_engine) -> None:
        self._store = file_store
        self._graph = graph_engine

        # run_id → asyncio.Task
        self._active: dict[str, asyncio.Task] = {}

        # run_id → stop event
        self._stop_events: dict[str, asyncio.Event] = {}

        # WebSocket broadcast callback — set by the WS router
        self._broadcast: Callable[[AgentEvent], None] | None = None

    def set_broadcaster(self, fn: Callable[[AgentEvent], None]) -> None:
        self._broadcast = fn

    # ─────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────

    async def start_run(self, agent: Agent, task: AgentTask) -> AgentRun:
        """Create a run record and launch the execution coroutine."""
        run_id = str(uuid.uuid4())[:12]
        run = AgentRun(
            id=run_id,
            agent_id=agent.id,
            task_id=task.id,
            task=task.task,
            project_id=task.project_id,
            status=RunStatus.running,
            started=datetime.utcnow(),
        )
        await asyncio.to_thread(self._store.create_run, run)
        await asyncio.to_thread(self._store.dequeue_task, task.id)

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
        # Pause is implemented as stop for now; a proper pause would need
        # checkpointing the conversation history to disk.
        return await self.stop_run(run_id)

    # ─────────────────────────────────────────
    # Execution loop
    # ─────────────────────────────────────────

    async def _execute(
        self,
        agent: Agent,
        task: AgentTask,
        run: AgentRun,
        stop: asyncio.Event,
    ) -> None:
        await self._log(run.id, LogLevel.info, f"Starting task: {task.task}")

        # Filter tool schemas to only those the agent is permitted to use
        allowed = {t.value for t in agent.tools} if agent.tools else {s["name"] for s in TOOL_SCHEMAS}
        tools = [s for s in TOOL_SCHEMAS if s["name"] in allowed]

        # Build the initial user message
        user_msg = task.task
        if task.context:
            user_msg = f"{task.task}\n\nContext:\n{task.context}"
        if task.project_id:
            user_msg += f"\n\nProject context ID: {task.project_id}"

        messages: list[dict] = [{"role": "user", "content": user_msg}]
        system = agent.effective_system_prompt()

        turns = 0
        final_text = ""

        try:
            while turns < agent.max_turns and not stop.is_set():
                turns += 1
                await self._log(run.id, LogLevel.info, f"Turn {turns}/{agent.max_turns}")
                await asyncio.to_thread(
                    self._store.update_run, run.id,
                    {"turns": turns, "progress": min(95, turns * (90 // agent.max_turns))}
                )

                response = await llm.chat(
                    messages,
                    system=system,
                    model=agent.model,
                    max_tokens=agent.max_tokens,
                    tools=tools,
                )

                # Collect text and tool calls from this turn (OpenAI format)
                turn_text = llm.get_text(response)
                tool_calls = llm.get_tool_calls(response)

                if turn_text:
                    final_text += turn_text + "\n"
                    await self._log(run.id, LogLevel.info, turn_text[:200] + ("…" if len(turn_text) > 200 else ""))

                # Append assistant turn to history
                messages.append(llm.assistant_message(response))

                # Stop if the model is done (no tool calls)
                if llm.is_done(response):
                    await self._log(run.id, LogLevel.ok, "Agent finished.")
                    break

                # Process tool calls and append results
                for tc in tool_calls:
                    args = llm.parse_tool_args(tc)
                    result = await self._dispatch_tool(run, agent, tc.function.name, args)
                    messages.append(llm.tool_result_message(tc.id, result))

            # Save result
            if final_text.strip():
                result_path = await asyncio.to_thread(
                    self._store.write_run_result, run.id, final_text.strip()
                )
                # Also save as a note in the knowledge base
                rc = ResourceCreate(
                    type=ResourceType.note,
                    title=f"Agent result: {task.task[:60]}",
                    description=f"Generated by {agent.name} agent, run {run.id}",
                    project_ids=[task.project_id] if task.project_id else [],
                    tags=["agent-output", agent.role.value],
                    content=final_text.strip(),
                )
                resource = await asyncio.to_thread(self._store.create_resource, rc)
                self._graph.add_resource(resource)

            await asyncio.to_thread(
                self._store.update_run, run.id,
                {"status": RunStatus.completed.value, "progress": 100, "finished": str(datetime.utcnow())}
            )
            await self._log(run.id, LogLevel.ok, "Run completed successfully.")
            await self._emit(AgentEvent(event="run_done", run_id=run.id, payload={"progress": 100}))

        except asyncio.CancelledError:
            await asyncio.to_thread(
                self._store.update_run, run.id,
                {"status": RunStatus.cancelled.value, "finished": str(datetime.utcnow())}
            )
            await self._log(run.id, LogLevel.warn, "Run cancelled.")
        except Exception as exc:
            msg = str(exc)
            await asyncio.to_thread(
                self._store.update_run, run.id,
                {"status": RunStatus.error.value, "error_msg": msg, "finished": str(datetime.utcnow())}
            )
            await self._log(run.id, LogLevel.error, f"Run failed: {msg}")
            await self._emit(AgentEvent(event="run_error", run_id=run.id, payload={"error": msg}))
        finally:
            self._stop_events.pop(run.id, None)

    # ─────────────────────────────────────────
    # Tool dispatcher
    # ─────────────────────────────────────────

    async def _dispatch_tool(self, run: AgentRun, agent: Agent, name: str, args: dict) -> Any:
        await self._log(run.id, LogLevel.tool, f"→ {name}({json.dumps(args)[:120]})")
        await self._emit(AgentEvent(
            event="tool_call", run_id=run.id,
            payload={"tool": name, "input": args}
        ))
        try:
            result = await self._call_tool(run, agent, name, args)
            await self._log(run.id, LogLevel.ok, f"← {name}: {str(result)[:120]}")
            return result
        except Exception as e:
            await self._log(run.id, LogLevel.error, f"← {name} error: {e}")
            return {"error": str(e)}

    async def _call_tool(self, run: AgentRun, agent: Agent, name: str, args: dict) -> Any:
        store = self._store

        if name == "list_projects":
            projects = await asyncio.to_thread(store.list_projects)
            return [{"id": p.id, "name": p.name, "status": p.status, "description": p.description} for p in projects]

        elif name == "read_project":
            detail = await asyncio.to_thread(store.get_project_detail, args["project_id"])
            if not detail:
                return {"error": "Project not found"}
            return detail.model_dump()

        elif name == "read_resource":
            content = await asyncio.to_thread(store.read_resource_content, args["resource_id"])
            if content is None:
                res = await asyncio.to_thread(store.get_resource, args["resource_id"])
                return {"error": "No content file"} if not res else {"title": res.title, "description": res.description}
            return {"content": content}

        elif name == "write_resource":
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
            resource = await asyncio.to_thread(store.create_resource, rc)
            self._graph.add_resource(resource)
            return {"id": resource.id, "title": resource.title, "path": resource.path}

        elif name == "create_decision":
            alts = [
                Alternative(title=a["title"], reason=a.get("reason", ""))
                for a in args.get("alternatives", [])
            ]
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
            decision = await asyncio.to_thread(store.create_decision, dc)
            return {"id": decision.id, "title": decision.title}

        elif name == "create_note":
            rc = ResourceCreate(
                type=ResourceType.note,
                title=args["title"],
                content=args.get("content", ""),
                project_ids=args.get("project_ids", []),
                tags=args.get("tags", []),
            )
            resource = await asyncio.to_thread(store.create_resource, rc)
            self._graph.add_resource(resource)
            return {"id": resource.id, "title": resource.title}

        elif name == "link_resources":
            ec = EdgeCreate(
                from_id=args["from_id"],
                to_id=args["to_id"],
                relation=RelationType(args["relation"]),
                note=args.get("note", ""),
            )
            edge = await asyncio.to_thread(store.create_edge, ec)
            self._graph.add_edge(edge)
            return {"edge_id": edge.id}

        elif name == "web_search":
            return await self._web_search(args["query"], args.get("max_results", 5))

        return {"error": f"Unknown tool: {name}"}

    async def _web_search(self, query: str, max_results: int = 5) -> dict:
        """
        Lightweight DuckDuckGo instant-answer search (no API key needed).
        For a richer result set, swap this for a Serper or Brave Search call.
        """
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_redirect": 1, "no_html": 1}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            data = resp.json()

        results = []
        abstract = data.get("AbstractText", "")
        if abstract:
            results.append({"title": data.get("Heading", query), "snippet": abstract, "url": data.get("AbstractURL", "")})

        for item in data.get("RelatedTopics", [])[:max_results]:
            if "Text" in item:
                results.append({"title": item.get("Text", "")[:80], "snippet": item.get("Text", ""), "url": item.get("FirstURL", "")})

        return {"query": query, "results": results[:max_results]}

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    async def _log(self, run_id: str, level: LogLevel, message: str) -> None:
        entry = LogEntry(level=level, message=message)
        await asyncio.to_thread(self._store.append_log, run_id, entry)
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
