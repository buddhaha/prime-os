"""
Unit tests for AgentRuntime.

LiteLLM is mocked throughout — these tests verify the tool dispatch loop,
DB persistence, and run lifecycle without making real LLM calls.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

from backend.services.agent_runtime import AgentRuntime
from backend.services.db_store import DBStore
from backend.models.agent import Agent, AgentRole, AgentTask, RunStatus, LogLevel
from backend.models.resource import ResourceType
from tests.conftest import project_create


# ─────────────────────────────────────────────
# Mock helpers
# ─────────────────────────────────────────────

def _stop_response(content: str = "Done."):
    """LiteLLM response: finish_reason=stop, no tool calls."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = []

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"

    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _tool_response(name: str, arguments: dict, call_id: str = "call_1"):
    """LiteLLM response: finish_reason=tool_calls, one function call."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    tc.model_dump.return_value = {
        "id": call_id, "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }

    msg = MagicMock()
    msg.content = ""
    msg.tool_calls = [tc]

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "tool_calls"

    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_task(task: str = "Summarise projects", project_id: str | None = None) -> AgentTask:
    return AgentTask(
        id="task-001",
        agent_id="researcher",
        task=task,
        project_id=project_id,
        context="",
    )


async def _wait_for_run(runtime: AgentRuntime, run_id: str, timeout: float = 3.0):
    """Wait until the asyncio task for run_id disappears from _active."""
    deadline = asyncio.get_event_loop().time() + timeout
    while run_id in runtime._active:
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(f"Run {run_id} did not complete within {timeout}s")
        await asyncio.sleep(0.05)


# ─────────────────────────────────────────────
# Run lifecycle
# ─────────────────────────────────────────────

async def test_start_run_persists_to_db(runtime: AgentRuntime, store: DBStore):
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _stop_response("Summary done.")
        agent = runtime.get_agent("researcher")
        run = await runtime.start_run(agent, _make_task())
        run_id = run.id

    await _wait_for_run(runtime, run_id)

    async with runtime._store() as s:
        persisted = await s.get_run(run_id)
    assert persisted is not None
    assert persisted.agent_id == "researcher"
    assert persisted.status == RunStatus.completed
    assert persisted.progress == 100


async def test_start_run_status_running_then_completed(runtime: AgentRuntime):
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _stop_response()
        agent = runtime.get_agent("writer")
        run = await runtime.start_run(agent, _make_task("Write something"))
        # Immediately after start_run the status is running
        assert run.status == RunStatus.running

    await _wait_for_run(runtime, run.id)

    async with runtime._store() as s:
        final = await s.get_run(run.id)
    assert final.status == RunStatus.completed


async def test_completed_run_saves_result_as_resource(runtime: AgentRuntime):
    result_text = "The projects are: Alpha, Beta, Gamma."
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _stop_response(result_text)
        agent = runtime.get_agent("researcher")
        run = await runtime.start_run(agent, _make_task())

    await _wait_for_run(runtime, run.id)

    async with runtime._store() as s:
        resources = await s.list_resources()
    agent_notes = [r for r in resources if "agent-output" in r.tags]
    assert len(agent_notes) == 1
    assert result_text in agent_notes[0].content


async def test_run_logs_written_to_db(runtime: AgentRuntime):
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _stop_response("All good.")
        agent = runtime.get_agent("analyst")
        run = await runtime.start_run(agent, _make_task("Analyse data"))

    await _wait_for_run(runtime, run.id)

    async with runtime._store() as s:
        logs = await s.get_run_logs(run.id)
    assert len(logs) > 0
    levels = {l.level for l in logs}
    assert LogLevel.info in levels


async def test_llm_error_marks_run_as_failed(runtime: AgentRuntime):
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = RuntimeError("LLM unavailable")
        agent = runtime.get_agent("researcher")
        run = await runtime.start_run(agent, _make_task())

    await _wait_for_run(runtime, run.id)

    async with runtime._store() as s:
        final = await s.get_run(run.id)
    assert final.status == RunStatus.error
    assert "LLM unavailable" in final.error_msg


async def test_stop_run_cancels_active_task(runtime: AgentRuntime):
    """start_run then immediately stop before the (slow) LLM responds."""
    event = asyncio.Event()

    async def slow_llm(*args, **kwargs):
        await event.wait()   # blocks until we release it
        return _stop_response()

    with patch("litellm.acompletion", new=slow_llm):
        agent = runtime.get_agent("monitor")
        run = await runtime.start_run(agent, _make_task("Watch forever"))
        run_id = run.id
        assert run_id in runtime._active

        ok = await runtime.stop_run(run_id)
        assert ok is True
        event.set()   # unblock so the task can exit cleanly

    await _wait_for_run(runtime, run_id)

    async with runtime._store() as s:
        final = await s.get_run(run_id)
    assert final.status == RunStatus.cancelled


async def test_stop_unknown_run_returns_false(runtime: AgentRuntime):
    ok = await runtime.stop_run("no-such-run")
    assert ok is False


# ─────────────────────────────────────────────
# Tool dispatch
# ─────────────────────────────────────────────

async def test_tool_list_projects(runtime: AgentRuntime, store: DBStore):
    """Agent calls list_projects → gets real project data from DB."""
    await store.create_project(project_create(name="Alpha"))

    responses = [
        _tool_response("list_projects", {}),
        _stop_response("Found projects."),
    ]
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = responses
        agent = runtime.get_agent("researcher")
        run = await runtime.start_run(agent, _make_task())

    await _wait_for_run(runtime, run.id)

    async with runtime._store() as s:
        final = await s.get_run(run.id)
    assert final.status == RunStatus.completed
    assert mock_llm.call_count == 2  # tool call + final turn


async def test_tool_write_resource(runtime: AgentRuntime, store: DBStore):
    """Agent calls write_resource → resource appears in DB."""
    p = await store.create_project(project_create(name="Beta"))

    responses = [
        _tool_response("write_resource", {
            "title": "Agent Note",
            "type":  "note",
            "content": "This is a note from the agent.",
            "project_ids": [p.id],
            "tags": ["agent-output"],
        }),
        _stop_response("Resource saved."),
    ]
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = responses
        agent = runtime.get_agent("writer")
        run = await runtime.start_run(agent, _make_task(project_id=p.id))

    await _wait_for_run(runtime, run.id)

    async with runtime._store() as s:
        resources = await s.list_resources(project_id=p.id)
    titles = [r.title for r in resources]
    assert "Agent Note" in titles


async def test_tool_web_search_returns_results(runtime: AgentRuntime):
    """web_search tool dispatches correctly and passes result back to LLM."""
    search_args = {"query": "asyncio best practices", "max_results": 3}
    responses = [
        _tool_response("web_search", search_args),
        _stop_response("Search complete."),
    ]
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm, \
         patch("httpx.AsyncClient") as mock_http:
        # Mock DuckDuckGo response
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "AbstractText": "asyncio is Python's async library",
            "Heading": "asyncio",
            "AbstractURL": "https://docs.python.org/asyncio",
            "RelatedTopics": [],
        }
        mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        mock_llm.side_effect = responses

        agent = runtime.get_agent("researcher")
        run = await runtime.start_run(agent, _make_task("Search for async patterns"))

    await _wait_for_run(runtime, run.id)

    async with runtime._store() as s:
        final = await s.get_run(run.id)
    assert final.status == RunStatus.completed

    # Second LLM call should have received the search result as a tool message
    second_call_messages = mock_llm.call_args_list[1][1]["messages"]
    tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    result_payload = json.loads(tool_msgs[0]["content"])
    assert "results" in result_payload


# ─────────────────────────────────────────────
# Agent registry
# ─────────────────────────────────────────────

async def test_list_agents_includes_defaults(runtime: AgentRuntime):
    agents = runtime.list_agents()
    ids = {a.id for a in agents}
    assert {"researcher", "writer", "analyst", "monitor", "coder"} == ids


async def test_register_custom_agent(runtime: AgentRuntime):
    custom = Agent(id="custom-1", name="Custom", role=AgentRole.custom)
    runtime.register_agent(custom)
    assert runtime.get_agent("custom-1") is not None
    assert runtime.get_agent("custom-1").name == "Custom"


async def test_get_agent_returns_none_for_unknown(runtime: AgentRuntime):
    assert runtime.get_agent("does-not-exist") is None
