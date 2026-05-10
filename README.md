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
prime-os.html  ←→  FastAPI (port 7474)  ←→  ~/PRIME/ (files)
                         ↕
                   NetworkX graph (in-memory)
                         ↕
                   Anthropic Claude (agents)
```

All structured data lives in `~/PRIME/` as JSON + Markdown files. No database for MVP. The knowledge graph is rebuilt in memory from those files on every server start.

Full architecture: see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Quick start

### Docker (recommended)

```bash
docker-compose up
open http://localhost:7474
```

That's it. On first boot, if `~/PRIME` is empty, the server seeds it automatically with the example projects. No separate setup step.

The API key is optional — projects, graph, and resources all work without one. Agents require it.

```bash
# With an API key (enables agent execution)
ANTHROPIC_API_KEY=sk-ant-... docker-compose up

# Or put it in .env
cp .env.example .env   # fill in key, then:
docker-compose up
```

**To re-seed** (wipes and rebuilds the data volume):

```bash
docker-compose run seed
```

To use a different data directory:

```bash
PRIME_DATA_DIR=/path/to/your/PRIME docker-compose up
```

---

### Local (Python)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY if you want to run agents

# 4. Seed example data (creates ~/PRIME/ with sample projects)
python -m backend.seed

# 5. Start the server
uvicorn backend.main:app --host 127.0.0.1 --port 7474 --reload

# 6. Open the frontend
open http://127.0.0.1:7474
```

---

## Project structure

```
prime-os.html          # Single-file frontend prototype
backend/
  main.py              # FastAPI app entry point
  config.py            # Pydantic Settings (reads .env)
  dependencies.py      # Shared dependency injection
  models/              # Pydantic data models
    project.py         # Project, Decision, Todo, Concept
    resource.py        # Resource (article/note/pdf/video/artifact), Edge
    agent.py           # Agent, AgentRun, LogEntry
    graph.py           # GraphNode, GraphEdge (wire format)
  services/
    file_store.py      # Read/write ~/PRIME filesystem
    graph_engine.py    # NetworkX DiGraph wrapper
    agent_runtime.py   # asyncio agent runner + Claude tool loop
  api/
    projects.py        # /api/projects routes
    graph.py           # /api/graph + /api/resources routes
    agents.py          # /api/agents + WebSocket routes
  seed.py              # Populate ~/PRIME with example data
skills/
  cowork/              # Skills for use in Cowork sessions
  agents/              # System prompts for PRIME agents
```

---

## Skills

The `skills/` directory contains two types of reusable prompts:

**Cowork skills** (`skills/cowork/`) are used during development sessions with Claude — design reviews, architecture decisions, research briefs. Load them in any Cowork session on this project.

**Agent skills** (`skills/agents/`) are the system prompts PRIME's built-in agents load when executing tasks. Editing these changes how the Research, Writer, Analyst, and Monitor agents behave.

See [skills/README.md](skills/README.md) for details.

---

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| 1 | Frontend wired to live API | ✅ Done |
| 2 | Docker Compose | ✅ Done |
| 3 | PostgreSQL (replace file store) | Planned |
| 3 | LiteLLM abstraction (Claude → Ollama → vLLM) | Planned |
| 4 | News view (RSS + X feed aggregation) | Planned |
| 5 | IBM pre-sales RAG view (doc ingestion + pgvector) | Planned |
| 6 | Langfuse observability + voice interface | Later |

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Optional. Required only to run agents |
| `PRIME_WORKSPACE` | `~/PRIME` | Where PRIME stores all data |
| `PRIME_HOST` | `127.0.0.1` | Server bind address |
| `PRIME_PORT` | `7474` | Server port |
