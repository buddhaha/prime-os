"""Knowledge graph endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.graph import GraphData, GraphNode
from ..models.resource import Resource, ResourceCreate, ResourceUpdate, Edge, EdgeCreate
from ..services.file_store import FileStore
from ..services.graph_engine import GraphEngine
from ..dependencies import get_store, get_graph

router = APIRouter(prefix="/api", tags=["graph"])


# ── Full graph ─────────────────────────────────

@router.get("/graph", response_model=GraphData)
async def get_graph(graph: GraphEngine = Depends(get_graph)):
    """Return the full knowledge graph for the frontend visualisation."""
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
    """Return the subgraph within `depth` hops of a node."""
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
    type: str | None = None,
    project_id: str | None = None,
    store: FileStore = Depends(get_store),
):
    return await asyncio.to_thread(store.list_resources, type, project_id)


@router.get("/resources/{resource_id}", response_model=Resource)
async def get_resource(resource_id: str, store: FileStore = Depends(get_store)):
    r = await asyncio.to_thread(store.get_resource, resource_id)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    return r


@router.get("/resources/{resource_id}/content")
async def get_resource_content(resource_id: str, store: FileStore = Depends(get_store)):
    content = await asyncio.to_thread(store.read_resource_content, resource_id)
    if content is None:
        raise HTTPException(status_code=404, detail="No content for this resource")
    return {"content": content}


@router.post("/resources", response_model=Resource, status_code=201)
async def create_resource(
    data: ResourceCreate,
    store: FileStore  = Depends(get_store),
    graph: GraphEngine = Depends(get_graph),
):
    resource = await asyncio.to_thread(store.create_resource, data)
    graph.add_resource(resource)
    return resource


@router.patch("/resources/{resource_id}", response_model=Resource)
async def update_resource(
    resource_id: str,
    data: ResourceUpdate,
    store: FileStore = Depends(get_store),
):
    r = await asyncio.to_thread(store.update_resource, resource_id, data)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    return r


# ── Edges ──────────────────────────────────────

@router.get("/graph/edges", response_model=list[Edge])
async def list_edges(store: FileStore = Depends(get_store)):
    return await asyncio.to_thread(store.list_edges)


@router.post("/graph/edges", response_model=Edge, status_code=201)
async def create_edge(
    data: EdgeCreate,
    store: FileStore  = Depends(get_store),
    graph: GraphEngine = Depends(get_graph),
):
    edge = await asyncio.to_thread(store.create_edge, data)
    graph.add_edge(edge)
    return edge


@router.delete("/graph/edges/{edge_id}", status_code=204)
async def delete_edge(
    edge_id: str,
    store: FileStore  = Depends(get_store),
):
    ok = await asyncio.to_thread(store.delete_edge, edge_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Edge not found")
