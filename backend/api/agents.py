"""Agent management endpoints + WebSocket for real-time events."""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from ..models.agent import (
    Agent, AgentCreate, AgentRun, AgentTask, AgentTaskCreate,
    AgentEvent, LogEntry,
)
from ..services.agent_runtime import AgentRuntime
from ..services.db_store import DBStore
from ..dependencies import get_runtime, get_store

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ── Fixed-path routes first (must precede /{agent_id}) ────────────────────────

@router.get("", response_model=list[Agent])
async def list_agents(runtime: AgentRuntime = Depends(get_runtime)):
    return runtime.list_agents()


@router.post("", response_model=Agent, status_code=201)
async def create_agent(data: AgentCreate, runtime: AgentRuntime = Depends(get_runtime)):
    agent = Agent(
        id=str(uuid.uuid4())[:8],
        name=data.name,
        role=data.role,
        emoji=data.emoji,
        description=data.description,
        model=data.model,
        system_prompt=data.system_prompt,
        tools=data.tools,
        max_tokens=data.max_tokens,
        max_turns=data.max_turns,
    )
    return runtime.register_agent(agent)


# ── Runs (fixed paths before /{agent_id}) ─────────────────────────────────────

@router.get("/runs", response_model=list[AgentRun])
async def list_runs(
    agent_id: str | None = None,
    status_filter: str | None = None,
    store: DBStore = Depends(get_store),
):
    return await store.list_runs(agent_id=agent_id, status=status_filter)


@router.get("/runs/{run_id}", response_model=AgentRun)
async def get_run(run_id: str, store: DBStore = Depends(get_store)):
    run = await store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/log", response_model=list[LogEntry])
async def get_run_log(run_id: str, store: DBStore = Depends(get_store)):
    return await store.get_run_logs(run_id)


@router.post("/runs/{run_id}/stop", status_code=200)
async def stop_run(run_id: str, runtime: AgentRuntime = Depends(get_runtime)):
    ok = await runtime.stop_run(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found or already finished")
    return {"stopped": run_id}


@router.post("/runs/{run_id}/pause", status_code=200)
async def pause_run(run_id: str, runtime: AgentRuntime = Depends(get_runtime)):
    ok = await runtime.pause_run(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found or already finished")
    return {"paused": run_id}


# ── WebSocket (fixed path) ────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    def broadcast(self, event: AgentEvent):
        payload = event.model_dump_json()
        dead = []
        for ws in self.active:
            try:
                asyncio.get_event_loop().call_soon_threadsafe(
                    asyncio.create_task,
                    ws.send_text(payload),
                )
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket, runtime: AgentRuntime = Depends(get_runtime)):
    """Connect to receive real-time agent events. Shape: { event, run_id, payload }"""
    await ws_manager.connect(websocket)
    runtime.set_broadcaster(ws_manager.broadcast)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("ping"):
                await websocket.send_text('{"pong": true}')
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ── Per-agent routes (wildcard — must be LAST) ────────────────────────────────

@router.get("/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str, runtime: AgentRuntime = Depends(get_runtime)):
    agent = runtime.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/tasks", response_model=AgentRun, status_code=202)
async def enqueue_and_run(
    agent_id: str,
    data: AgentTaskCreate,
    runtime: AgentRuntime = Depends(get_runtime),
):
    agent = runtime.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    task = AgentTask(
        id=str(uuid.uuid4())[:8],
        agent_id=agent_id,
        task=data.task,
        project_id=data.project_id,
        priority=data.priority,
        context=data.context,
    )
    return await runtime.start_run(agent, task)
