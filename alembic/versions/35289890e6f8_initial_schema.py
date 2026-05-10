"""initial_schema

Revision ID: 35289890e6f8
Revises:
Create Date: 2026-05-10

Creates all PRIME OS tables:
  projects, decisions, todos, concepts, resources, resource_projects, edges
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "35289890e6f8"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── projects ──────────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id",           sa.String(),  primary_key=True),
        sa.Column("name",         sa.String(),  nullable=False),
        sa.Column("emoji",        sa.String(),  nullable=True,  server_default="📁"),
        sa.Column("description",  sa.Text(),    nullable=True,  server_default=""),
        sa.Column("color",        sa.String(),  nullable=True,  server_default="#00d4ff"),
        sa.Column("status",       sa.String(),  nullable=True,  server_default="active"),
        sa.Column("project_type", sa.String(),  nullable=True,  server_default="personal"),
        sa.Column("tags",         postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("progress",     sa.String(),  nullable=True,  server_default="0"),
        sa.Column("created",      sa.Date(),    nullable=True),
        sa.Column("updated",      sa.Date(),    nullable=True),
    )

    # ── decisions ─────────────────────────────────────────────────────────────
    op.create_table(
        "decisions",
        sa.Column("id",           sa.String(), primary_key=True),
        sa.Column("project_id",   sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title",        sa.String(), nullable=False),
        sa.Column("date",         sa.Date(),   nullable=True),
        sa.Column("type",         sa.String(), nullable=True, server_default="decision"),
        sa.Column("status",       sa.String(), nullable=True, server_default="accepted"),
        sa.Column("context",      sa.Text(),   nullable=True, server_default=""),
        sa.Column("body",         sa.Text(),   nullable=True, server_default=""),
        sa.Column("consequences", sa.Text(),   nullable=True, server_default=""),
        sa.Column("alternatives", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_decisions_project_id", "decisions", ["project_id"])

    # ── todos ─────────────────────────────────────────────────────────────────
    op.create_table(
        "todos",
        sa.Column("id",         sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text",       sa.String(), nullable=False),
        sa.Column("status",     sa.String(), nullable=True, server_default="open"),
        sa.Column("priority",   sa.String(), nullable=True, server_default="medium"),
        sa.Column("section",    sa.String(), nullable=True, server_default="Backlog"),
        sa.Column("tags",       postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("created",    sa.Date(),   nullable=True),
        sa.Column("completed",  sa.Date(),   nullable=True),
    )
    op.create_index("ix_todos_project_id", "todos", ["project_id"])

    # ── concepts ──────────────────────────────────────────────────────────────
    op.create_table(
        "concepts",
        sa.Column("id",         sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",       sa.String(), nullable=False),
        sa.Column("desc",       sa.Text(),   nullable=True, server_default=""),
    )
    op.create_index("ix_concepts_project_id", "concepts", ["project_id"])

    # ── resources ─────────────────────────────────────────────────────────────
    op.create_table(
        "resources",
        sa.Column("id",          sa.String(), primary_key=True),
        sa.Column("type",        sa.String(), nullable=False),
        sa.Column("title",       sa.String(), nullable=False),
        sa.Column("description", sa.Text(),   nullable=True, server_default=""),
        sa.Column("source_url",  sa.String(), nullable=True),
        sa.Column("tags",        postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("content",     sa.Text(),   nullable=True, server_default=""),
        sa.Column("created",     sa.Date(),   nullable=True),
    )

    # ── resource_projects (many-to-many) ──────────────────────────────────────
    op.create_table(
        "resource_projects",
        sa.Column("resource_id", sa.String(), sa.ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("project_id",  sa.String(), sa.ForeignKey("projects.id",  ondelete="CASCADE"), primary_key=True),
    )

    # ── edges ─────────────────────────────────────────────────────────────────
    op.create_table(
        "edges",
        sa.Column("id",       sa.String(), primary_key=True),
        sa.Column("from_id",  sa.String(), nullable=False),
        sa.Column("to_id",    sa.String(), nullable=False),
        sa.Column("relation", sa.String(), nullable=True, server_default="related_to"),
        sa.Column("note",     sa.String(), nullable=True, server_default=""),
        sa.UniqueConstraint("from_id", "to_id", "relation", name="uq_edge"),
    )


def downgrade() -> None:
    op.drop_table("edges")
    op.drop_table("resource_projects")
    op.drop_table("resources")
    op.drop_table("concepts")
    op.drop_table("todos")
    op.drop_table("decisions")
    op.drop_table("projects")
