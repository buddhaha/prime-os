"""add resource status/origin + proposals table

Revision ID: 9869086366eb
Revises: 35289890e6f8
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "9869086366eb"
down_revision = "35289890e6f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Add status + origin columns to resources ──────────────────────────────
    op.add_column("resources", sa.Column("status", sa.String(), nullable=True, server_default="inbox"))
    op.add_column("resources", sa.Column("origin", sa.String(), nullable=True, server_default="manual"))

    # ── proposals table ───────────────────────────────────────────────────────
    op.create_table(
        "proposals",
        sa.Column("id",            sa.String(), primary_key=True),
        sa.Column("project_id",    sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title",         sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("source_url",    sa.String(), nullable=True),
        sa.Column("read_time",     sa.String(), nullable=True),
        sa.Column("why_relevant",  sa.Text(),   nullable=True, server_default=""),
        sa.Column("takeaways",     postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gap_type",      sa.String(), nullable=True, server_default=""),
        sa.Column("gap_label",     sa.String(), nullable=True, server_default=""),
        sa.Column("status",        sa.String(), nullable=True, server_default="pending"),
        sa.Column("created",       sa.Date(),   nullable=True),
    )
    op.create_index("ix_proposals_project_id", "proposals", ["project_id"])
    op.create_index("ix_proposals_status",     "proposals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_proposals_status",     table_name="proposals")
    op.drop_index("ix_proposals_project_id", table_name="proposals")
    op.drop_table("proposals")
    op.drop_column("resources", "origin")
    op.drop_column("resources", "status")
