import enum
from datetime import datetime
from typing import List

from pgvector.sqlalchemy import Vector
from sqlalchemy import TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import get_settings

settings = get_settings()


class DocSourceTypeEnum(enum.Enum):
    FILE = "file"
    URL = "url"


class DocStatusEnum(enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


# This is how its done, https://docs.sqlalchemy.org/en/20/orm/declarative_styles.html
class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "document_table"

    # Types: https://docs.sqlalchemy.org/en/20/core/types.html
    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[DocSourceTypeEnum]
    source_reference: Mapped[str]
    title: Mapped[str]
    status: Mapped[DocStatusEnum]
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    # https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#one-to-many
    chunks: Mapped[List["Chunk"]] = relationship(back_populates="document")


class Chunk(Base):
    __tablename__ = "chunk_table"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document_table.id"))
    document: Mapped["Document"] = relationship(back_populates="chunks")
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
