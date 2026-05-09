"""
Agent models — agent definitions, runs, task queue, and log entries.

On disk layout:
  ~/PRIME/agents/
    registry.json          ← list of Agent objects
    queue.json             ← ordered list of AgentTask objects
    runs/
      {run_id}/
        run.json           ← AgentRun metadata
        log.jsonl          ← one LogEntry per line (append-only)
        result.md          ← final output written by the agent
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Agent definition
# ─────────────────────────────────────────────

class AgentRole(str, Enum):
    research  = "research"
    writer    = "writer"
    analyst   = "analyst"
    monitor   = "monitor"
    coder     = "coder"
    custom    = "custom"


# Default system prompts per role — agents can override
ROLE_PROMPTS: dict[AgentRole, str] = {
    AgentRole.research: (
        "You are a research agent for PRIME OS. Your job is to gather information, "
        "synthesise sources, and return clear, structured findings. Always cite your sources. "
        "Save your final report using the write_resource tool."
    ),
    AgentRole.writer: (
        "You are a writing agent for PRIME OS. You write documents, ADRs, summaries, and briefs "
        "in a clear, concise style. Use the read_resource tool to gather context, and "
        "write_resource to save your output."
    ),
    AgentRole.analyst: (
        "You are a data and analysis agent for PRIME OS. You analyse data, compute metrics, "
        "identify patterns, and produce reports. Use file tools to read data and save results."
    ),
    AgentRole.monitor: (
        "You are a monitoring agent for PRIME OS. You check sources, inboxes, and conditions "
        "on a schedule and surface important changes or alerts."
    ),
    AgentRole.coder: (
        "You are a coding agent for PRIME OS. You write, review, and improve code. "
        "Read existing files for context and write your output back to the appropriate location."
    ),
    AgentRole.custom: "You are a general-purpose agent for PRIME OS.",
}


class AgentTool(str, Enum):
    """Tools an agent can be granted access to."""
    web_search      = "web_search"
    read_resource   = "read_resource"
    write_resource  = "write_resource"
    create_decision = "create_decision"
    create_note     = "create_note"
    link_resources  = "link_resources"
    read_project    = "read_project"
    list_projects   = "list_projects"


class Agent(BaseModel):
    """Stored as an entry in ~/PRIME/agents/registry.json"""
    id:            str
    name:          str
    role:          AgentRole
    emoji:         str  = "🤖"
    description:   str  = ""

    # Claude model to use
    model:         str  = "claude-opus-4-6"

    # System prompt — defaults to ROLE_PROMPTS[role] if empty
    system_prompt: str  = ""

    # Which tools this agent is allowed to call
    tools:         list[AgentTool] = Field(default_factory=list)

    # Max tokens per turn; max turns per run
    max_tokens:    int  = 4096
    max_turns:     int  = 20

    created:       datetime = Field(default_factory=datetime.utcnow)
    updated:       datetime = Field(default_factory=datetime.utcnow)

    def effective_system_prompt(self) -> str:
        return self.system_prompt or ROLE_PROMPTS.get(self.role, ROLE_PROMPTS[AgentRole.custom])


class AgentCreate(BaseModel):
    name:          str
    role:          AgentRole
    emoji:         str  = "🤖"
    description:   str  = ""
    model:         str  = "claude-opus-4-6"
    system_prompt: str  = ""
    tools:         list[AgentTool] = Field(default_factory=list)
    max_tokens:    int  = 4096
    max_turns:     int  = 20


# ─────────────────────────────────────────────
# Agent task (queue item)
# ─────────────────────────────────────────────

class AgentTask(BaseModel):
    """A unit of work queued for an agent. Stored in ~/PRIME/agents/queue.json"""
    id:          str
    agent_id:    str
    task:        str          # human description of what to do
    project_id:  str | None  = None   # optional project context
    priority:    int          = 5     # 1 (high) – 10 (low)
    created:     datetime     = Field(default_factory=datetime.utcnow)
    # Extra context injected into the agent's first user message
    context:     str          = ""


class AgentTaskCreate(BaseModel):
    agent_id:   str
    task:       str
    project_id: str | None = None
    priority:   int         = 5
    context:    str         = ""


# ─────────────────────────────────────────────
# Agent run
# ─────────────────────────────────────────────

class RunStatus(str, Enum):
    queued    = "queued"
    running   = "running"
    paused    = "paused"
    completed = "completed"
    error     = "error"
    cancelled = "cancelled"


class AgentRun(BaseModel):
    """
    Stored as ~/PRIME/agents/runs/{id}/run.json.
    Log lines appended to log.jsonl; result written to result.md.
    """
    id:          str
    agent_id:    str
    task_id:     str
    task:        str
    project_id:  str | None  = None
    status:      RunStatus   = RunStatus.queued
    progress:    int         = 0    # 0–100 estimate
    turns:       int         = 0    # how many Claude turns used
    started:     datetime | None = None
    finished:    datetime | None = None
    error_msg:   str         = ""

    # Populated when returning run details (not stored in run.json)
    log:         list["LogEntry"] = Field(default_factory=list)
    result_path: str | None = None


# ─────────────────────────────────────────────
# Log entry
# ─────────────────────────────────────────────

class LogLevel(str, Enum):
    info  = "info"
    ok    = "ok"
    warn  = "warn"
    error = "error"
    tool  = "tool"    # agent called a tool


class LogEntry(BaseModel):
    """One line in ~/PRIME/agents/runs/{run_id}/log.jsonl"""
    ts:      datetime = Field(default_factory=datetime.utcnow)
    level:   LogLevel = LogLevel.info
    message: str
    # If this entry is a tool call/result
    tool:    str | None = None
    input:   Any | None = None
    output:  Any | None = None


# ─────────────────────────────────────────────
# WebSocket event sent to the frontend
# ─────────────────────────────────────────────

class AgentEvent(BaseModel):
    """Real-time event pushed over WS /ws/agents"""
    event:   str        # "run_started" | "log" | "progress" | "run_done" | "run_error"
    run_id:  str
    payload: Any
