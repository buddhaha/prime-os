"""
Integration tests for /api/agents endpoints.

Uses agent_client fixture (real test DB + real AgentRuntime + mocked LiteLLM).
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _litellm_stop_response(content: str = "Task complete."):
    """Minimal LiteLLM response that causes the agent loop to stop immediately."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = []

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"

    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ─────────────────────────────────────────────
# Agent registry
# ─────────────────────────────────────────────

async def test_list_agents_returns_five_defaults(agent_client):
    r = await agent_client.get("/api/agents")
    assert r.status_code == 200
    agents = r.json()
    assert len(agents) == 5
    ids = {a["id"] for a in agents}
    assert {"researcher", "writer", "analyst", "monitor", "coder"} == ids


async def test_get_agent_researcher(agent_client):
    r = await agent_client.get("/api/agents/researcher")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "researcher"
    assert data["role"] == "research"


async def test_get_agent_not_found(agent_client):
    r = await agent_client.get("/api/agents/nonexistent")
    assert r.status_code == 404


async def test_create_custom_agent(agent_client):
    payload = {
        "name": "Summariser",
        "role": "writer",
        "emoji": "📝",
        "description": "Summarises long docs",
        "model": "",
        "system_prompt": "",
        "tools": [],
        "max_tokens": 2048,
        "max_turns": 5,
    }
    r = await agent_client.post("/api/agents", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Summariser"
    assert data["role"] == "writer"


# ─────────────────────────────────────────────
# Runs — listing and retrieval
# ─────────────────────────────────────────────

async def test_list_runs_empty(agent_client):
    r = await agent_client.get("/api/agents/runs")
    assert r.status_code == 200
    assert r.json() == []


async def test_get_run_not_found(agent_client):
    r = await agent_client.get("/api/agents/runs/no-such-run")
    assert r.status_code == 404


async def test_get_run_log_empty(agent_client):
    r = await agent_client.get("/api/agents/runs/no-such-run/log")
    assert r.status_code == 200
    assert r.json() == []


# ─────────────────────────────────────────────
# Starting a run via the API
# ─────────────────────────────────────────────

async def test_enqueue_task_returns_run(agent_client):
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _litellm_stop_response("Projects listed.")

        r = await agent_client.post(
            "/api/agents/researcher/tasks",
            json={"agent_id": "researcher", "task": "List all projects", "priority": 5, "context": ""},
        )
        assert r.status_code == 202
        data = r.json()
        assert data["agent_id"] == "researcher"
        assert data["status"] == "running"
        run_id = data["id"]

    # Wait for the asyncio task to finish
    await asyncio.sleep(0.3)

    r2 = await agent_client.get(f"/api/agents/runs/{run_id}")
    assert r2.status_code == 200
    assert r2.json()["status"] == "completed"


async def test_enqueue_task_unknown_agent(agent_client):
    r = await agent_client.post(
        "/api/agents/ghost/tasks",
        json={"agent_id": "ghost", "task": "Do something", "priority": 5, "context": ""},
    )
    assert r.status_code == 404


async def test_run_logs_written_after_completion(agent_client):
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _litellm_stop_response("All done.")

        r = await agent_client.post(
            "/api/agents/writer/tasks",
            json={"agent_id": "writer", "task": "Write a brief", "priority": 5, "context": ""},
        )
        run_id = r.json()["id"]

    await asyncio.sleep(0.3)

    logs_r = await agent_client.get(f"/api/agents/runs/{run_id}/log")
    assert logs_r.status_code == 200
    logs = logs_r.json()
    assert len(logs) > 0
    messages = [l["message"] for l in logs]
    assert any("completed" in m.lower() or "finished" in m.lower() for m in messages)


# ─────────────────────────────────────────────
# Stop a run
# ─────────────────────────────────────────────

async def test_stop_nonexistent_run(agent_client):
    r = await agent_client.post("/api/agents/runs/no-such-run/stop")
    assert r.status_code == 404
