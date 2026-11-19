"""knowledge index: documents and chunks with pgvector

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "documents",
        sa.Column("project", sa.String(64), nullable=False),
        sa.Column("rel_path", sa.Text, nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column(
            "indexed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("project", "rel_path"),
    )
    op.create_table(
        "chunks",
        sa.Column("project", sa.String(64), nullable=False),
        sa.Column("rel_path", sa.Text, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("heading", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.PrimaryKeyConstraint("project", "rel_path", "ordinal"),
        sa.ForeignKeyConstraint(
            ["project", "rel_path"],
            ["documents.project", "documents.rel_path"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("documents")
