# PRIME OS

Personal intelligence system. Jarvis-style dashboard for managing projects, knowledge, and autonomous agents — local-first, runs on your machine.

---

## What it is

PRIME gives you five views:

- **Daily Dashboard** — your day at a glance: active todos, agent activity, upcoming decisions
- **Projects Hub** — decision timelines (ADRs), todos with sections, concepts, document links
- **Knowledge Graph** — everything connected: articles, notes, PDFs, videos, artifacts — visualised with D3
- **Agents** — spawn research, writing, and analysis agents; watch them work in real time via WebSocket
- **Voice / Chat** — conversational interface to query your knowledge base and control the system

---

## Architecture

```
prime-os.html  ←→  FastAPI (port 7474)  ←→  PostgreSQL 16
                         ↕
                   NetworkX graph (in-memory)
                         ↕
                   LiteLLM  →  Claude / Ollama / OpenAI
```

Structured data lives in PostgreSQL. The knowledge graph is built in memory on startup from the DB. Agents run as asyncio tasks, persist run state and logs to the DB, and stream events to the frontend over WebSocket.

Full architecture: see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Quick start

### Docker (recommended)

```bash
cp .env.example .env   # fill in PRIME_MODEL + provider key
docker-compose up
open http://localhost:7474
```

On first boot the server seeds the DB automatically with example projects.

```bash
# Anthropic (default)
ANTHROPIC_API_KEY=sk-ant-... docker-compose up

# Local Ollama (no API key needed)
PRIME_MODEL=ollama/llama3.1 docker-compose up

# OpenAI
PRIME_MODEL=gpt-4o OPENAI_API_KEY=sk-... docker-compose up
```

**Run tests:**

```bash
docker-compose run --rm test
```

**Re-seed the database:**

```bash
docker-compose run --rm seed
```

---

### Local (Python)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit: set PRIME_MODEL + provider key

# Run migrations
DATABASE_URL=postgresql+asyncpg://prime:prime_dev@localhost:5432/prime alembic upgrade head

# Start the server
uvicorn backend.main:app --host 127.0.0.1 --port 7474 --reload

open http://127.0.0.1:7474
```

---

## LLM configuration

PRIME uses [LiteLLM](https://docs.litellm.ai) to route agent tasks to any supported model. Set `PRIME_MODEL` in `.env`:

| Model string | Provider | Key needed |
|---|---|---|
| `claude-sonnet-4-6` | Anthropic (cloud) | `ANTHROPIC_API_KEY` |
| `claude-opus-4-7` | Anthropic (cloud) | `ANTHROPIC_API_KEY` |
| `ollama/llama3.1` | Ollama (local) | none |
| `ollama/mistral` | Ollama (local) | none |
| `ollama/qwen2.5-coder` | Ollama (local) | none |
| `gpt-4o` | OpenAI (cloud) | `OPENAI_API_KEY` |

All other LiteLLM-supported providers work the same way — set the model string and the relevant key.

---

## Project structure

```
prime-os.html          # Single-file frontend prototype (D3 + WebSocket)
backend/
  main.py              # FastAPI app entry point + lifespan
  config.py            # Pydantic Settings (reads .env)
  database.py          # SQLAlchemy ORM models + async engine
  dependencies.py      # Shared dependency injection
  models/              # Pydantic data models
    project.py         # Project, Decision, Todo, Concept
    resource.py        # Resource, Edge, Proposal
    agent.py           # Agent, AgentRun, LogEntry
    graph.py           # GraphNode, GraphEdge (D3 wire format)
  services/
    db_store.py        # Async PostgreSQL CRUD (all entities)
    graph_engine.py    # NetworkX DiGraph wrapper
    agent_runtime.py   # asyncio agent runner + LiteLLM tool loop
    proposal_engine.py # Gap detection + Claude-powered proposal generation
  api/
    projects.py        # /api/projects routes
    graph.py           # /api/graph, /api/resources, /api/proposals routes
    agents.py          # /api/agents + WebSocket routes
  seed.py              # Populate DB with example data
alembic/               # Database migrations
skills/
  cowork/              # Skills for use in Cowork sessions
  agents/              # System prompts for PRIME agents
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `PRIME_MODEL` | `claude-sonnet-4-6` | LiteLLM model string for agents |
| `ANTHROPIC_API_KEY` | — | Required when using Claude models |
| `OPENAI_API_KEY` | — | Required when using OpenAI models |
| `OLLAMA_API_BASE` | `http://localhost:11434` | Ollama server URL |
| `DATABASE_URL` | local postgres | PostgreSQL connection string |
| `PRIME_HOST` | `127.0.0.1` | Server bind address |
| `PRIME_PORT` | `7474` | Server port |
| `PRIME_API_KEY` | — | If set, requires `X-API-Key` header on all `/api` routes |

---

## Roadmap

| Phase | What | Status |
|---|---|---|
| 1 | Frontend wired to live API | ✅ Done |
| 2 | Docker Compose + PostgreSQL | ✅ Done |
| 2 | Agent runtime + persistent runs/logs | ✅ Done |
| 2 | Architecture quick-wins (migrate service, edge delete, API key guard) | ✅ Done |
| 3 | LiteLLM abstraction — Claude, Ollama, OpenAI | ✅ Done |
| 4 | News view — RSS + feed aggregation | Planned |
| 5 | RAG view — doc ingestion + pgvector semantic search | Planned |
| 6 | Frontend migration — Vite + React | Planned |
| 7 | Langfuse observability + voice interface | Later |

---

## Skills

The `skills/` directory contains two types of reusable prompts:

**Cowork skills** (`skills/cowork/`) — used during development sessions with Claude. Load them in any Cowork session on this project.

**Agent skills** (`skills/agents/`) — system prompts for PRIME's built-in agents. Editing these changes how Researcher, Writer, Analyst, and Monitor agents behave.

See [skills/README.md](skills/README.md) for details.
