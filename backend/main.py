"""
PRIME OS — FastAPI application entry point.

Run with:
    uvicorn backend.main:app --host 127.0.0.1 --port 7474 --reload

Or via the helper script:
    python -m backend
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import settings
from .services.file_store    import FileStore
from .services.graph_engine  import GraphEngine
from .services.agent_runtime import AgentRuntime
from .dependencies           import init_dependencies
from .api                    import projects, graph, agents

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("prime")


# ─────────────────────────────────────────────
# Lifespan — startup / shutdown
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(f"PRIME OS starting. Workspace: {settings.workspace_path}")

    # 1. Initialise core services
    store   = FileStore(settings.workspace_path)
    graph   = GraphEngine()
    runtime = AgentRuntime(store, graph)
    init_dependencies(store, graph, runtime)

    # 2. Build the knowledge graph from disk
    log.info("Building knowledge graph…")
    projects_list  = store.list_projects()
    all_decisions  = []
    for proj in projects_list:
        for dec in store.list_decisions(proj.id):
            all_decisions.append((proj.id, dec))
    resources_list = store.list_resources()
    edges_list     = store.list_edges()

    graph.rebuild(
        projects=projects_list,
        decisions=all_decisions,
        resources=resources_list,
        edges=edges_list,
    )
    stats = graph.stats()
    log.info(f"Graph ready: {stats['node_count']} nodes, {stats['edge_count']} edges")

    yield  # server is running

    # Shutdown: cancel any active agent runs
    log.info("PRIME OS shutting down. Cancelling active runs…")
    for task in asyncio.all_tasks():
        if task.get_name().startswith("run-"):
            task.cancel()


# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────

app = FastAPI(
    title="PRIME OS API",
    description="Personal intelligence system — projects, knowledge graph, agents.",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers
app.include_router(projects.router)
app.include_router(graph.router)
app.include_router(agents.router)


# ── Health check
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ── Serve the frontend prototype from the repo root
# In production you'd point this at a built dist/ folder.
@app.get("/")
async def serve_frontend():
    import pathlib
    frontend = pathlib.Path(__file__).parent.parent / "prime-os.html"
    if frontend.exists():
        return FileResponse(str(frontend))
    return {"message": "PRIME OS API is running. Frontend not found at repo root."}


# ─────────────────────────────────────────────
# Module runner
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
