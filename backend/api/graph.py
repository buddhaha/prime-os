"""Knowledge graph endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.graph import GraphData, GraphNode
from ..models.resource import Resource, ResourceCreate, ResourceUpdate, Edge, EdgeCreate
from ..services.db_store import DBStore
from ..services.graph_engine import GraphEngine
from ..dependencies import get_store, get_graph

router = APIRouter(prefix="/api", tags=["graph"])


# ── Full graph ─────────────────────────────────

@router.get("/graph", response_model=GraphData)
async def get_graph(graph: GraphEngine = Depends(get_graph)):
    return graph.get_graph()


@router.get("/graph/stats")
async def graph_stats(graph: GraphEngine = Depends(get_graph)):
    return graph.stats()


@router.get("/graph/node/{node_id}", response_model=GraphData)
async def get_node_neighborhood(
    node_id: str,
    depth: int = Query(1, ge=1, le=3),
    graph: GraphEngine = Depends(get_graph),
):
    return graph.neighbors(node_id, depth=depth)


@router.get("/graph/search", response_model=list[GraphNode])
async def search_graph(
    q: str = Query(..., min_length=1),
    graph: GraphEngine = Depends(get_graph),
):
    return graph.search_nodes(q)


# ── Resources ──────────────────────────────────

@router.get("/resources", response_model=list[Resource])
async def list_resources(
    project_id: str | None = None,
    store: DBStore = Depends(get_store),
):
    return await store.list_resources(project_id=project_id)


@router.post("/resources", response_model=Resource, status_code=201)
async def create_resource(
    data: ResourceCreate,
    store: DBStore      = Depends(get_store),
    graph: GraphEngine  = Depends(get_graph),
):
    resource = await store.create_resource(data)
    graph.add_resource(resource)
    return resource


@router.patch("/resources/{resource_id}", response_model=Resource)
async def update_resource(
    resource_id: str,
    data: ResourceUpdate,
    store: DBStore = Depends(get_store),
):
    r = await store.update_resource(resource_id, data)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    return r


# ── Edges ──────────────────────────────────────

@router.get("/graph/edges", response_model=list[Edge])
async def list_edges(store: DBStore = Depends(get_store)):
    return await store.list_edges()


@router.post("/graph/edges", response_model=Edge, status_code=201)
async def create_edge(
    data: EdgeCreate,
    store: DBStore      = Depends(get_store),
    graph: GraphEngine  = Depends(get_graph),
):
    edge = await store.create_edge(data)
    graph.add_edge(edge)
    return edge
