"""
Agent management endpoints + WebSocket for real-time events.

NOTE: Agent persistence (registry, runs, queue) is Phase 2 — not yet in the DB.
Store-dependent endpoints return stubs so the UI doesn't 500.
Runtime controls (stop/pause) and WebSocket work as-is.
"""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from ..models.agent import (
    Agent, AgentCreate, AgentRun, AgentTask, AgentTaskCreate,
    AgentEvent, LogEntry,
)
from ..services.agent_runtime import AgentRuntime
from ..dependencies import get_runtime

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ── Agent registry (stubbed — Phase 2) ────────────────────────────────────────
# NOTE: fixed-path routes must come before /{agent_id}

@router.get("", response_model=list[Agent])
async def list_agents():
    return []


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_agent(data: AgentCreate):
    raise HTTPException(status_code=501, detail="Agent persistence not yet implemented")


# ── Task queue (stubbed) ───────────────────────────────────────────────────────

@router.get("/queue", response_model=list[AgentTask])
async def get_queue():
    return []


@router.post("/queue", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def enqueue_task(data: AgentTaskCreate):
    raise HTTPException(status_code=501, detail="Agent persistence not yet implemented")


# ── Runs (stubbed) ─────────────────────────────────────────────────────────────

@router.get("/runs", response_model=list[AgentRun])
async def list_runs(agent_id: str | None = None, status_filter: str | None = None):
    return []


@router.get("/runs/{run_id}", response_model=AgentRun)
async def get_run(run_id: str):
    raise HTTPException(status_code=404, detail="Run not found")


@router.get("/runs/{run_id}/log", response_model=list[LogEntry])
async def get_run_log(run_id: str):
    return []


@router.get("/runs/{run_id}/result")
async def get_run_result(run_id: str):
    raise HTTPException(status_code=404, detail="No result yet")


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


# ── Per-agent routes (wildcard — must be LAST) ────────────────────────────────

@router.get("/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str):
    raise HTTPException(status_code=404, detail="Agent not found")


@router.post("/{agent_id}/tasks", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def enqueue_and_run(agent_id: str, data: AgentTaskCreate):
    raise HTTPException(status_code=501, detail="Agent persistence not yet implemented")


# ── WebSocket — real-time agent events ────────────────────────────────────────

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
