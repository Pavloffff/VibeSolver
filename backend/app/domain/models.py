import enum
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ImportState(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, insert_default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Import(Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImportedFile(Base):
    __tablename__ = "imported_files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sources.id"), nullable=False)
    branch: Mapped[str] = mapped_column(Text, nullable=False, insert_default="")
    path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    import_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("imports.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_revision: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourceSnapshotFile(Base):
    __tablename__ = "source_snapshot_files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("source_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    branch: Mapped[str] = mapped_column(Text, nullable=False, default="")
    path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ProjectIndex(Base):
    __tablename__ = "project_indexes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    index_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="not_started")
    active_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("index_runs.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IndexRun(Base):
    __tablename__ = "index_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_index_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("project_indexes.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("source_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parser_version: Mapped[str] = mapped_column(Text, nullable=False)
    chunker_version: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workspace_models.id", ondelete="SET NULL"), nullable=True
    )
    embedding_model_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    files_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostics: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndexChunk(Base):
    __tablename__ = "index_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("index_runs.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_file_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("source_snapshot_files.id", ondelete="CASCADE"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    branch: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', content)", persisted=True), nullable=False
    )
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ModelProviderConnection(Base):
    __tablename__ = "model_provider_connections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkspaceModel(Base):
    __tablename__ = "workspace_models"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_connection_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("model_provider_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_model_id: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProjectModelAssignment(Base):
    __tablename__ = "project_model_assignments"

    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, primary_key=True)
    model_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workspace_models.id", ondelete="CASCADE"), nullable=False
    )
