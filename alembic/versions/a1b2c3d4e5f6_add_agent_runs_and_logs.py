"""add agent_runs and agent_logs tables

Revision ID: a1b2c3d4e5f6
Revises: 9869086366eb
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "9869086366eb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id",         sa.String(),  primary_key=True),
        sa.Column("agent_id",   sa.String(),  nullable=False),
        sa.Column("agent_name", sa.String(),  nullable=False, server_default=""),
        sa.Column("task",       sa.Text(),    nullable=False),
        sa.Column("project_id", sa.String(),  nullable=True),
        sa.Column("status",     sa.String(),  nullable=False, server_default="running"),
        sa.Column("progress",   sa.Integer(), nullable=False, server_default="0"),
        sa.Column("turns",      sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started",    sa.DateTime(), nullable=True),
        sa.Column("finished",   sa.DateTime(), nullable=True),
        sa.Column("error_msg",  sa.Text(),    nullable=False, server_default=""),
    )
    op.create_index("ix_agent_runs_status",   "agent_runs", ["status"])
    op.create_index("ix_agent_runs_agent_id", "agent_runs", ["agent_id"])

    op.create_table(
        "agent_logs",
        sa.Column("id",      sa.String(),   primary_key=True),
        sa.Column("run_id",  sa.String(),   sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts",      sa.DateTime(), nullable=False),
        sa.Column("level",   sa.String(),   nullable=False, server_default="info"),
        sa.Column("message", sa.Text(),     nullable=False, server_default=""),
    )
    op.create_index("ix_agent_logs_run_id", "agent_logs", ["run_id"])


def downgrade() -> None:
    op.drop_table("agent_logs")
    op.drop_table("agent_runs")
