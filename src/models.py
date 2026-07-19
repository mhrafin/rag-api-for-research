import enum
import uuid
from datetime import datetime
from typing import List, Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    TIMESTAMP,
    Enum,
    ForeignKey,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import get_settings

settings = get_settings()

# Switched to using literal due to alembic not picking up changes. Current way is yet to be tested. https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html#using-python-enum-or-pep-586-literal-types-in-the-type-map
DocSourceTypeEnum = Literal["FILE", "URL"]

DocStatusEnum = Literal["QUEUED", "PROCESSING", "CHUNKED", "READY", "FAILED"]


# This is how its done, https://docs.sqlalchemy.org/en/20/orm/declarative_styles.html
class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "document_table"

    # Types: https://docs.sqlalchemy.org/en/20/core/types.html
    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[DocSourceTypeEnum] = mapped_column(
        Enum("FILE", "URL", name="doc_source_type_enum")
    )
    source_reference: Mapped[str]
    content: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[DocStatusEnum] = mapped_column(
        Enum(
            "QUEUED", "PROCESSING", "CHUNKED", "READY", "FAILED", name="doc_status_enum"
        ),
        server_default="QUEUED",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    # https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#one-to-many
    chunks: Mapped[List["Chunk"]] = relationship(back_populates="document")


class Chunk(Base):
    __tablename__ = "chunk_table"

    # no two rows in the chunks table can share the same (document_id, chunk_index) pair.
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document_table.id", ondelete="CASCADE")
    )
    document: Mapped["Document"] = relationship(back_populates="chunks")
    # Need a chunk_uuid to trace back to the chunk
    chunk_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    chunk_index: Mapped[int]
    content: Mapped[str]
    token_count: Mapped[int] = mapped_column(nullable=True)
    # https://github.com/pgvector/pgvector-python#sqlalchemy
    embedding: Mapped[List[float]] = mapped_column(
        Vector(settings.embedding_dim), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
