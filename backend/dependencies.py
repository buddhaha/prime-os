"""
FastAPI dependency injectors.
"""

from .database import AsyncSessionLocal
from .services.graph_engine  import GraphEngine
from .services.agent_runtime import AgentRuntime
from .services.db_store      import DBStore

# Module-level singletons for graph + runtime (initialised in main.py lifespan)
_graph:   GraphEngine  | None = None
_runtime: AgentRuntime | None = None


def init_dependencies(graph: GraphEngine, runtime: AgentRuntime) -> None:
    global _graph, _runtime
    _graph   = graph
    _runtime = runtime


# ── Per-request DB session + store ─────────────────────────────────────────

async def get_store() -> DBStore:
    """
    Yields a DBStore backed by a fresh async session.
    Use as a FastAPI Depends() — the session is committed and closed automatically.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield DBStore(session)


# ── Singletons ──────────────────────────────────────────────────────────────

def get_graph() -> GraphEngine:
    assert _graph is not None, "GraphEngine not initialised"
    return _graph


def get_runtime() -> AgentRuntime:
    assert _runtime is not None, "AgentRuntime not initialised"
    return _runtime
