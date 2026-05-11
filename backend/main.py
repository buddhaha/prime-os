"""
PRIME OS — FastAPI application entry point.

Run with:
    uvicorn backend.main:app --host 127.0.0.1 --port 7474 --reload

Or via Docker Compose:
    docker-compose up
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import settings
from .database import AsyncSessionLocal
from .services.graph_engine  import GraphEngine
from .services.agent_runtime import AgentRuntime
from .services.db_store      import DBStore
from .dependencies           import init_dependencies
from .api                    import projects, graph, agents

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("prime")


def _run_migrations() -> None:
    """Run Alembic migrations synchronously (called via asyncio.to_thread)."""
    import os
    from alembic.config import Config
    from alembic import command

    # Locate alembic.ini relative to this file's repo root
    import pathlib
    ini = pathlib.Path(__file__).parent.parent / "alembic.ini"
    cfg = Config(str(ini))
    # Explicitly set script_location so %(here)s interpolation in alembic.ini
    # works correctly when called programmatically (e.g. from within Docker)
    cfg.set_main_option("script_location", str(ini.parent / "alembic"))
    # Override URL so Alembic uses the same DATABASE_URL as the app
    # Alembic needs a sync driver — swap asyncpg → psycopg2 for the migration run
    sync_url = settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, "head")


# ─────────────────────────────────────────────
# Lifespan — startup / shutdown
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(f"PRIME OS starting. DB: {settings.database_url.split('@')[-1]}")

    # 1. Run Alembic migrations (idempotent — applies any pending migrations)
    log.info("Running database migrations…")
    await asyncio.to_thread(_run_migrations)
    log.info("Database migrations complete.")

    # 2. Initialise graph + runtime singletons
    graph_engine = GraphEngine()
    runtime      = AgentRuntime(None, graph_engine)
    init_dependencies(graph_engine, runtime)

    # 3. Auto-seed if DB is empty
    async with AsyncSessionLocal() as session:
        async with session.begin():
            store = DBStore(session)
            existing = await store.list_projects()
            if not existing:
                log.info("Database is empty — seeding…")
                from .seed import seed_db
                await seed_db(store)
                log.info("Seed complete.")

    # 4. Build in-memory knowledge graph from DB
    log.info("Building knowledge graph…")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            store        = DBStore(session)
            all_projects  = await store.list_projects()
            all_resources = await store.list_resources()
            all_edges     = await store.list_edges()
            all_decisions = []
            for proj in all_projects:
                for dec in await store.list_decisions(proj.id):
                    all_decisions.append((proj.id, dec))

    graph_engine.rebuild(
        projects=all_projects,
        decisions=all_decisions,
        resources=all_resources,
        edges=all_edges,
    )
    stats = graph_engine.stats()
    log.info(f"Graph ready: {stats['node_count']} nodes, {stats['edge_count']} edges")

    yield  # server is running

    log.info("PRIME OS shutting down.")


# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────

app = FastAPI(
    title="PRIME OS API",
    description="Personal intelligence system — projects, knowledge graph, agents.",
    version="0.2.0",
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

app.include_router(projects.router)
app.include_router(graph.router)
app.include_router(agents.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


@app.get("/")
async def serve_frontend():
    import pathlib
    frontend = pathlib.Path(__file__).parent.parent / "prime-os.html"
    if frontend.exists():
        return FileResponse(str(frontend))
    return {"message": "PRIME OS API is running. Frontend not found at repo root."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
