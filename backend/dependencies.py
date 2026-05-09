"""
FastAPI dependency injectors.
Single instances shared across all requests (app-level singletons).
"""

from functools import lru_cache

from .services.file_store   import FileStore
from .services.graph_engine import GraphEngine
from .services.agent_runtime import AgentRuntime

# Module-level singletons — initialised in main.py lifespan
_store:   FileStore   | None = None
_graph:   GraphEngine | None = None
_runtime: AgentRuntime | None = None


def init_dependencies(store: FileStore, graph: GraphEngine, runtime: AgentRuntime) -> None:
    global _store, _graph, _runtime
    _store   = store
    _graph   = graph
    _runtime = runtime


def get_store() -> FileStore:
    assert _store is not None, "FileStore not initialised"
    return _store


def get_graph() -> GraphEngine:
    assert _graph is not None, "GraphEngine not initialised"
    return _graph


def get_runtime() -> AgentRuntime:
    assert _runtime is not None, "AgentRuntime not initialised"
    return _runtime
