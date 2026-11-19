from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    func,
)

metadata = MetaData()

documents = Table(
    "documents",
    metadata,
    Column("project", String(64), nullable=False),
    Column("rel_path", Text, nullable=False),
    Column("digest", String(64), nullable=False),
    Column("model", Text, nullable=False),
    Column("indexed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("project", "rel_path"),
)

# Untyped `vector`: a model with another dimension needs no migration (spec 4).
chunks = Table(
    "chunks",
    metadata,
    Column("project", String(64), nullable=False),
    Column("rel_path", Text, nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("heading", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("embedding", Vector(), nullable=False),
    PrimaryKeyConstraint("project", "rel_path", "ordinal"),
    ForeignKeyConstraint(
        ["project", "rel_path"],
        ["documents.project", "documents.rel_path"],
        ondelete="CASCADE",
    ),
)
