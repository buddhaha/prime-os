# PRIME OS — Architecture

Personal intelligence system. Local-first, Python backend, Claude agents.

---

## System overview

```
┌───────────────────────────────────────────────────────┐
│               Frontend (prime-os.html)                │
│          Future: React SPA or Electron app            │
└──────────────────────┬────────────────────────────────┘
                       │  REST + WebSocket
                       │  http://127.0.0.1:7474
┌──────────────────────▼────────────────────────────────┐
│              FastAPI Server (backend/main.py)         │
│                                                       │
│  GET/POST /api/projects     ← projects, decisions,    │
│  GET/POST /api/resources       todos, concepts        │
│  GET      /api/graph        ← knowledge graph JSON    │
│  GET/POST /api/agents       ← agent registry + runs  │
│  WS       /api/agents/ws   ← real-time agent events  │
└───────┬───────────────┬──────────────┬───────────────┘
        │               │              │
┌───────▼──────┐ ┌──────▼──────┐ ┌────▼────────────────┐
│   DBStore    │ │ GraphEngine │ │   AgentRuntime      │
│              │ │             │ │                     │
│  SQLAlchemy  │ │  NetworkX   │ │ asyncio tasks       │
│  async ORM   │ │  DiGraph    │ │ LiteLLM calls       │
│  PostgreSQL  │ │  in-memory  │ │ tool dispatch       │
└───────┬──────┘ └─────────────┘ └────────┬────────────┘
        │                                  │
        │  PostgreSQL (prime DB)            │  LiteLLM → Claude / OpenAI / Ollama / vLLM
        └──────────────────────────────────┘
```

---

## Workspace layout

```
~/PRIME/
├── projects/
│   └── {project-slug}/
│       ├── project.json          # Project metadata
│       ├── decisions/
│       │   └── ADR-001-title.md  # YAML frontmatter + Markdown
│       ├── todos.json
│       └── concepts.json
├── knowledge/
│   ├── nodes.json                # list[Resource]
│   ├── edges.json                # list[Edge]
│   ├── articles/                 # saved Markdown articles
│   ├── notes/                    # personal notes (.md)
│   ├── pdfs/                     # original PDF files
│   ├── videos/                   # metadata + transcripts
│   └── artifacts/                # designs, exports, code
└── agents/
    ├── registry.json             # list[Agent]
    ├── queue.json                # list[AgentTask]
    └── runs/
        └── {run-id}/
            ├── run.json          # AgentRun metadata
            ├── log.jsonl         # append-only log stream
            └── result.md         # agent's final output
```

Everything is plain files. Human-readable, git-trackable, no migrations.

---

## Data models

### Project
```json
{
  "id": "personal-ai-os",
  "name": "Personal AI OS",
  "emoji": "🤖",
  "color": "#00d4ff",
  "status": "active",
  "tags": ["software", "ai"]
}
```

### Decision (ADR) — stored as Markdown
```markdown
---
id: ADR-002
project: personal-ai-os
title: HTML-first prototype
date: 2026-05-09
type: adr
status: accepted
alternatives:
  - title: React SPA
    reason: Adds build tooling before UX is validated
---

## Context
Need to validate UX before committing to a stack.

## Decision
Build a rich single-file HTML prototype.

## Consequences
Fast iteration. Tech stack decision deferred.
```

### Resource (knowledge graph node)
```json
{
  "id": "a1b2c3d4",
  "type": "article",           // article | note | pdf | video | artifact
  "title": "RDF vs Property Graph",
  "description": "Trade-off analysis...",
  "path": "knowledge/articles/rdf-vs-property-graph.md",
  "source_url": "https://...",
  "project_ids": ["personal-ai-os"],
  "tags": ["knowledge-graph", "database"]
}
```

### Edge
```json
{
  "id": "e9f8a7b6",
  "from_id": "personal-ai-os",
  "to_id": "a1b2c3d4",
  "relation": "contains",      // contains | references | cites | related_to | supersedes
  "note": "Research for ADR-002"
}
```

### Agent
```json
{
  "id": "x1y2z3w4",
  "name": "Research",
  "role": "research",          // research | writer | analyst | monitor | coder | custom
  "model": "claude-opus-4-6",
  "tools": ["web_search", "write_resource", "create_note", "link_resources"]
}
```

### AgentRun
```json
{
  "id": "run-abc123",
  "agent_id": "x1y2z3w4",
  "task": "Compare RDF vs property graph for personal KG",
  "status": "running",         // queued | running | paused | completed | error | cancelled
  "progress": 62,
  "turns": 4,
  "started": "2026-05-09T14:22:00"
}
```

---

## Knowledge graph

**Nodes** = Projects + Decisions + Resources  
**Edges** = explicit (from `edges.json`) + auto-generated (project→decision on creation)

Node types and their graph weight:

| Type       | Emoji | Color     | Weight |
|------------|-------|-----------|--------|
| project    | 📁    | `#00d4ff` | 3 (hub)|
| decision   | ⚖️    | `#3b82f6` | 2      |
| article    | 📰    | `#3b82f6` | 2      |
| note       | 📝    | `#10b981` | 2      |
| pdf        | 📄    | `#f59e0b` | 2      |
| video      | 🎬    | `#ec4899` | 2      |
| artifact   | 🎨    | `#8b5cf6` | 2      |

The `GraphEngine` wraps a NetworkX DiGraph. On startup `main.py` calls
`graph.rebuild()` with all data from FileStore. Incremental updates
(add_project, add_resource, add_edge) keep the graph live without a
full rebuild.

The frontend fetches `GET /api/graph` → `{nodes, edges}` and renders
with D3 force simulation.

---

## Agent runtime

Each agent run is an `asyncio.Task`. The loop:

```
1. Dequeue task from queue.json
2. Build system prompt (role default + overrides)
3. POST to Claude API (streaming, tool_use enabled)
4. For each tool_use block → dispatch to Python handler
5. Append results to messages[], continue loop
6. On end_turn with no tools → write result.md, save as Note
7. Update run.json status → completed / error
8. Broadcast WS event to all connected frontends
```

**Tools agents can call:**

| Tool              | What it does                              |
|-------------------|-------------------------------------------|
| `list_projects`   | Get all projects                          |
| `read_project`    | Get project detail (decisions, todos)     |
| `read_resource`   | Read a resource's Markdown content        |
| `write_resource`  | Save a new resource to the knowledge base |
| `create_decision` | Write an ADR to a project                 |
| `create_note`     | Quick note → knowledge base               |
| `link_resources`  | Add an edge to the graph                  |
| `web_search`      | DuckDuckGo instant answers (no key needed)|

---

## API reference

```
GET  /api/health

GET  /api/projects                        list all
POST /api/projects                        create
GET  /api/projects/{id}                   full detail (decisions + todos + concepts)
PATCH /api/projects/{id}                  update metadata

GET  /api/projects/{id}/decisions         list
POST /api/projects/{id}/decisions         create ADR
GET  /api/projects/{id}/todos             list
POST /api/projects/{id}/todos             create
PATCH /api/projects/{id}/todos/{todo_id}  toggle / update

GET  /api/resources                       list (filter: ?type=note&project_id=x)
POST /api/resources                       create
GET  /api/resources/{id}                  get
GET  /api/resources/{id}/content          get raw Markdown

GET  /api/graph                           full graph {nodes, edges}
GET  /api/graph/node/{id}?depth=1         neighbourhood subgraph
GET  /api/graph/search?q=rdf              fuzzy node search
GET  /api/graph/stats                     NetworkX stats
POST /api/graph/edges                     add edge
DELETE /api/graph/edges/{id}              remove edge

GET  /api/agents                          list registered agents
POST /api/agents                          register new agent
POST /api/agents/{id}/tasks               queue + immediately start a run
GET  /api/agents/runs                     list runs (filter: ?agent_id=x&status=running)
GET  /api/agents/runs/{run_id}            run detail + last 20 log lines
GET  /api/agents/runs/{run_id}/log        full log
GET  /api/agents/runs/{run_id}/result     final Markdown output
POST /api/agents/runs/{run_id}/stop       cancel run
WS   /api/agents/ws                       real-time events stream
```

---

## Getting started

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and optionally PRIME_WORKSPACE

# 3. Seed example data
python -m backend.seed

# 4. Start the server
uvicorn backend.main:app --host 127.0.0.1 --port 7474 --reload

# 5. Open the frontend
open jarvis-os.html
# Or visit http://127.0.0.1:7474 (serves jarvis-os.html directly)
```

---

## Open decisions

| # | Question | Status |
|---|----------|--------|
| 1 | Knowledge graph schema: RDF vs property graph | **Open** — Research agent task queued |
| 2 | Voice API: Whisper local vs browser Web Speech | Open |
| 3 | Frontend framework: keep HTML or migrate to React/Svelte | Deferred until UX validated |
| 4 | File watcher: watchdog integration for live graph updates | Not started |
| 5 | Multi-device sync strategy | Deferred (git-based sync is simplest) |
