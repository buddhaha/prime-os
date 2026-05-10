"""Agent management endpoints + WebSocket for real-time events."""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from ..models.agent import (
    Agent, AgentCreate, AgentRun, AgentTask, AgentTaskCreate,
    AgentEvent, LogEntry, RunStatus,
)
from ..services.file_store import FileStore
from ..services.agent_runtime import AgentRuntime
from ..dependencies import get_store, get_runtime

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ── Agent registry ─────────────────────────────
# NOTE: All fixed-path routes MUST come before /{agent_id} to avoid wildcard capture.

@router.get("", response_model=list[Agent])
async def list_agents(store: FileStore = Depends(get_store)):
    return await asyncio.to_thread(store.list_agents)


@router.post("", response_model=Agent, status_code=status.HTTP_201_CREATED)
async def create_agent(data: AgentCreate, store: FileStore = Depends(get_store)):
    return await asyncio.to_thread(store.create_agent, data)


# ── Task queue ─────────────────────────────────

@router.get("/queue", response_model=list[AgentTask])
async def get_queue(store: FileStore = Depends(get_store)):
    return await asyncio.to_thread(store.list_queue)


@router.post("/queue", response_model=AgentTask, status_code=status.HTTP_201_CREATED)
async def enqueue_task(data: AgentTaskCreate, store: FileStore = Depends(get_store)):
    """Enqueue a task without starting it immediately."""
    return await asyncio.to_thread(store.enqueue_task, data)


# ── Runs ───────────────────────────────────────

@router.get("/runs", response_model=list[AgentRun])
async def list_runs(
    agent_id: str | None = None,
    status_filter: str | None = None,
    store: FileStore = Depends(get_store),
):
    return await asyncio.to_thread(store.list_runs, agent_id, status_filter)


@router.get("/runs/{run_id}", response_model=AgentRun)
async def get_run(run_id: str, store: FileStore = Depends(get_store)):
    run = await asyncio.to_thread(store.get_run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/log", response_model=list[LogEntry])
async def get_run_log(run_id: str, store: FileStore = Depends(get_store)):
    return await asyncio.to_thread(store.read_run_log, run_id)


@router.get("/runs/{run_id}/result")
async def get_run_result(run_id: str, store: FileStore = Depends(get_store)):
    content = await asyncio.to_thread(store.read_run_result, run_id)
    if content is None:
        raise HTTPException(status_code=404, detail="No result yet")
    return {"content": content}


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


# ── Per-agent routes (wildcard — must be LAST) ──

@router.get("/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str, store: FileStore = Depends(get_store)):
    agent = await asyncio.to_thread(store.get_agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/tasks", response_model=AgentRun, status_code=status.HTTP_201_CREATED)
async def enqueue_and_run(
    agent_id: str,
    data: AgentTaskCreate,
    store:   FileStore    = Depends(get_store),
    runtime: AgentRuntime = Depends(get_runtime),
):
    """
    Enqueue a task for an agent AND immediately start it.
    For deferred execution, POST to /api/agents/queue instead.
    """
    agent = await asyncio.to_thread(store.get_agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    data.agent_id = agent_id
    task = await asyncio.to_thread(store.enqueue_task, data)
    run = await runtime.start_run(agent, task)
    return run


# ── WebSocket — real-time agent events ─────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    def broadcast(self, event: AgentEvent):
        """Synchronous broadcast — called from AgentRuntime."""
        payload = event.model_dump_json()
        dead = []
        for ws in self.active:
            try:
                # Schedule send on the event loop
                asyncio.get_event_loop().call_soon_threadsafe(
                    asyncio.create_task,
                    ws.send_text(payload),
                )
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


ws_manager = ConnectionManager()


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket, runtime: AgentRuntime = Depends(get_runtime)):
    """
    Connect to receive real-time agent events.
    Event shape: { event, run_id, payload }
    """
    await ws_manager.connect(websocket)
    runtime.set_broadcaster(ws_manager.broadcast)
    try:
        while True:
            # Keep connection alive; client can send {"ping": true}
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("ping"):
                await websocket.send_text('{"pong": true}')
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
