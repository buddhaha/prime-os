"""
PRIME OS — async SQLAlchemy engine, session factory, and ORM table definitions.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Integer, String, Text,
    Table, MetaData, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from .config import settings


# ─────────────────────────────────────────────
# Engine + session factory
# ─────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    echo=False,          # set True to log all SQL
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a session and closes it after the request."""
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    """Create all tables if they don't exist (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ─────────────────────────────────────────────
# Declarative base
# ─────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────
# Association table — resource ↔ project (many-to-many)
# ─────────────────────────────────────────────

resource_projects = Table(
    "resource_projects",
    Base.metadata,
    Column("resource_id", String, ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True),
    Column("project_id",  String, ForeignKey("projects.id",  ondelete="CASCADE"), primary_key=True),
)


# ─────────────────────────────────────────────
# ORM models
# ─────────────────────────────────────────────

class ProjectRow(Base):
    __tablename__ = "projects"

    id           = Column(String, primary_key=True, default=new_id)
    name         = Column(String, nullable=False)
    emoji        = Column(String, default="📁")
    description  = Column(Text,   default="")
    color        = Column(String, default="#00d4ff")
    status       = Column(String, default="active")
    project_type = Column(String, default="personal")
    tags         = Column(ARRAY(String), default=list)
    progress     = Column(String, default="0")   # stored as str to match Pydantic model
    created      = Column(Date,   default=date.today)
    updated      = Column(Date,   default=date.today)

    decisions  = relationship("DecisionRow",  back_populates="project", cascade="all, delete-orphan")
    todos      = relationship("TodoRow",      back_populates="project", cascade="all, delete-orphan")
    concepts   = relationship("ConceptRow",   back_populates="project", cascade="all, delete-orphan")
    resources  = relationship("ResourceRow",  secondary=resource_projects, back_populates="projects")


class DecisionRow(Base):
    __tablename__ = "decisions"

    id           = Column(String, primary_key=True, default=new_id)
    project_id   = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title        = Column(String, nullable=False)
    date         = Column(Date,   default=date.today)
    type         = Column(String, default="decision")
    status       = Column(String, default="accepted")
    context      = Column(Text,   default="")
    body         = Column(Text,   default="")
    consequences = Column(Text,   default="")
    alternatives = Column(JSONB,  default=list)

    project = relationship("ProjectRow", back_populates="decisions")


class TodoRow(Base):
    __tablename__ = "todos"

    id         = Column(String, primary_key=True, default=new_id)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    text       = Column(String, nullable=False)
    status     = Column(String, default="open")
    priority   = Column(String, default="medium")
    section    = Column(String, default="Backlog")
    tags       = Column(ARRAY(String), default=list)
    created    = Column(Date, default=date.today)
    completed  = Column(Date, nullable=True)

    project = relationship("ProjectRow", back_populates="todos")


class ConceptRow(Base):
    __tablename__ = "concepts"

    id         = Column(String, primary_key=True, default=new_id)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String, nullable=False)
    desc       = Column(Text,   default="")

    project = relationship("ProjectRow", back_populates="concepts")


class ResourceRow(Base):
    __tablename__ = "resources"

    id          = Column(String, primary_key=True, default=new_id)
    type        = Column(String, nullable=False)
    title       = Column(String, nullable=False)
    description = Column(Text,   default="")
    source_url  = Column(String, nullable=True)
    tags        = Column(ARRAY(String), default=list)
    content     = Column(Text,   default="")
    created     = Column(Date,   default=date.today)
    status      = Column(String, default="inbox")     # inbox | reading | processed | archived
    origin      = Column(String, default="manual")    # manual | suggested

    projects = relationship("ProjectRow", secondary=resource_projects, back_populates="resources")


class ProposalRow(Base):
    __tablename__ = "proposals"

    id            = Column(String, primary_key=True, default=new_id)
    project_id    = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title         = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    source_url    = Column(String, nullable=True)
    read_time     = Column(String, nullable=True)
    why_relevant  = Column(Text,   default="")
    takeaways     = Column(JSONB,  default=list)   # list[str]
    gap_type      = Column(String, default="")     # "concept" | "todo" | "decision"
    gap_label     = Column(String, default="")     # name of the triggering gap
    status        = Column(String, default="pending")  # pending | accepted | dismissed
    created       = Column(Date,   default=date.today)

    project = relationship("ProjectRow")


class EdgeRow(Base):
    __tablename__ = "edges"

    id       = Column(String, primary_key=True, default=new_id)
    from_id  = Column(String, nullable=False)
    to_id    = Column(String, nullable=False)
    relation = Column(String, default="related_to")
    note     = Column(String, default="")

    __table_args__ = (
        UniqueConstraint("from_id", "to_id", "relation", name="uq_edge"),
    )


class AgentRunRow(Base):
    __tablename__ = "agent_runs"

    id         = Column(String,  primary_key=True, default=new_id)
    agent_id   = Column(String,  nullable=False)
    agent_name = Column(String,  nullable=False, default="")
    task       = Column(Text,    nullable=False)
    project_id = Column(String,  nullable=True)
    status     = Column(String,  nullable=False, default="running")
    progress   = Column(Integer, nullable=False, default=0)
    turns      = Column(Integer, nullable=False, default=0)
    started    = Column(DateTime, nullable=True)
    finished   = Column(DateTime, nullable=True)
    error_msg  = Column(Text,    nullable=False, default="")

    logs = relationship("AgentLogRow", back_populates="run", cascade="all, delete-orphan",
                        order_by="AgentLogRow.ts")


class AgentLogRow(Base):
    __tablename__ = "agent_logs"

    id      = Column(String,   primary_key=True, default=new_id)
    run_id  = Column(String,   ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    ts      = Column(DateTime, nullable=False)
    level   = Column(String,   nullable=False, default="info")
    message = Column(Text,     nullable=False, default="")

    run = relationship("AgentRunRow", back_populates="logs")
