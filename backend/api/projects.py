"""Projects, Decisions, Todos, Concepts — REST endpoints."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..models.project import (
    Project, ProjectCreate, ProjectDetail,
    Decision, DecisionCreate,
    Todo, TodoCreate, TodoUpdate,
    Concept,
)
from ..services.file_store import FileStore
from ..services.graph_engine import GraphEngine
from ..dependencies import get_store, get_graph

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ── Projects ──────────────────────────────────

@router.get("/", response_model=list[Project])
async def list_projects(store: FileStore = Depends(get_store)):
    return await asyncio.to_thread(store.list_projects)


@router.post("/", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    store: FileStore  = Depends(get_store),
    graph: GraphEngine = Depends(get_graph),
):
    project = await asyncio.to_thread(store.create_project, data)
    graph.add_project(project)
    return project


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str, store: FileStore = Depends(get_store)):
    detail = await asyncio.to_thread(store.get_project_detail, project_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Project not found")
    return detail


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    updates: dict,
    store: FileStore = Depends(get_store),
):
    project = await asyncio.to_thread(store.update_project, project_id, updates)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ── Decisions ──────────────────────────────────

@router.get("/{project_id}/decisions", response_model=list[Decision])
async def list_decisions(project_id: str, store: FileStore = Depends(get_store)):
    return await asyncio.to_thread(store.list_decisions, project_id)


@router.post("/{project_id}/decisions", response_model=Decision, status_code=status.HTTP_201_CREATED)
async def create_decision(
    project_id: str,
    data: DecisionCreate,
    store: FileStore = Depends(get_store),
):
    data.project_id = project_id
    return await asyncio.to_thread(store.create_decision, data)


# ── Todos ──────────────────────────────────────

@router.get("/{project_id}/todos", response_model=list[Todo])
async def list_todos(project_id: str, store: FileStore = Depends(get_store)):
    return await asyncio.to_thread(store.list_todos, project_id)


@router.post("/{project_id}/todos", response_model=Todo, status_code=status.HTTP_201_CREATED)
async def create_todo(
    project_id: str,
    data: TodoCreate,
    store: FileStore = Depends(get_store),
):
    return await asyncio.to_thread(store.create_todo, project_id, data)


@router.patch("/{project_id}/todos/{todo_id}", response_model=Todo)
async def update_todo(
    project_id: str,
    todo_id: str,
    data: TodoUpdate,
    store: FileStore = Depends(get_store),
):
    todo = await asyncio.to_thread(store.update_todo, project_id, todo_id, data)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo


# ── Concepts ───────────────────────────────────

@router.get("/{project_id}/concepts", response_model=list[Concept])
async def list_concepts(project_id: str, store: FileStore = Depends(get_store)):
    return await asyncio.to_thread(store.list_concepts, project_id)


@router.post("/{project_id}/concepts", response_model=Concept, status_code=status.HTTP_201_CREATED)
async def create_concept(
    project_id: str,
    name: str,
    desc: str = "",
    store: FileStore = Depends(get_store),
):
    return await asyncio.to_thread(store.create_concept, project_id, name, desc)
