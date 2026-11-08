from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.adapter.celery_app import celery_app
from app.adapter.config import Settings, get_settings
from app.adapter.db import to_sync_dsn
from app.adapter.model_providers.providers import embed_texts
from app.adapter.s3 import make_s3_client
from app.domain.models import IndexChunk, IndexRun, ProjectIndex, SourceSnapshotFile
from app.usecase.code_indexer import chunk_code_file
from app.usecase.documentation_indexer import chunk_document_file
from app.usecase.user_flow_indexer import parse_approved_flows, render_flow_for_search

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
EMBEDDING_BATCH_SIZE = 48


@dataclass(frozen=True, slots=True)
class EmbeddingTarget:
    provider_type: str
    base_url: str
    model_id: str
    api_key: str | None


@dataclass(frozen=True, slots=True)
class ChunkPayload:
    snapshot_file_id: int
    content_hash: str
    path: str
    branch: str
    start_line: int | None
    end_line: int | None
    symbol: str | None
    content: str
    embedding_text: str
    metadata: dict[str, Any]


def get_index_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(to_sync_dsn(get_settings().database_url))
    return _engine


def get_index_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_index_engine(), expire_on_commit=False)
    return _session_factory


def run_project_index(run_id: int) -> None:
    settings = get_settings()
    with get_index_session_factory()() as session:
        run = session.get(IndexRun, run_id)
        if run is None:
            return
        project_index = session.get(ProjectIndex, run.project_index_id)
        if project_index is None:
            raise RuntimeError("project index not found")
        run.status = "running"
        run.progress = 0
        run.started_at = datetime.now(UTC)
        project_index.status = "running"
        session.commit()
        try:
            _build_index(session, run, project_index, settings)
        except Exception as exc:
            session.rollback()
            failed_run = session.get(IndexRun, run_id)
            failed_index = session.get(ProjectIndex, project_index.id)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.error = _human_index_error(exc)
                failed_run.finished_at = datetime.now(UTC)
                if failed_index is not None:
                    failed_index.status = "failed"
                session.commit()
            raise


def _build_index(
    session: Session, run: IndexRun, project_index: ProjectIndex, settings: Settings
) -> None:
    snapshot_files = list(
        session.scalars(
            select(SourceSnapshotFile)
            .where(SourceSnapshotFile.snapshot_id == run.snapshot_id)
            .order_by(SourceSnapshotFile.branch, SourceSnapshotFile.path)
        )
    )
    if not snapshot_files:
        raise ValueError("the selected snapshot contains no files to index")
    target = _embedding_target(session, run.embedding_model_id, settings)
    s3 = make_s3_client(settings)
    run.files_total = len(snapshot_files)
    diagnostics: list[dict[str, str]] = []
    pending: list[ChunkPayload] = []
    chunks_total = 0

    for file_number, stored_file in enumerate(snapshot_files, start=1):
        body_result = s3.get_object(Bucket=settings.s3_bucket_raw, Key=stored_file.storage_key)[
            "Body"
        ]
        content = body_result if isinstance(body_result, bytes) else body_result.read()
        try:
            file_chunks, diagnostic = _parse_file(
                project_index.index_type,
                stored_file.id,
                stored_file.path,
                stored_file.branch,
                stored_file.content_hash,
                content,
                stored_file.metadata_json,
            )
            pending.extend(file_chunks)
            if diagnostic is not None:
                diagnostics.append({"path": stored_file.path, "message": diagnostic})
        except ValueError as exc:
            diagnostics.append({"path": stored_file.path, "message": str(exc)})
        while len(pending) >= EMBEDDING_BATCH_SIZE:
            batch = pending[:EMBEDDING_BATCH_SIZE]
            del pending[:EMBEDDING_BATCH_SIZE]
            chunks_total += _persist_chunk_batch(session, run, target, batch)
        run.progress = int(file_number * 99 / len(snapshot_files))
        run.chunks_total = chunks_total
        run.diagnostics = diagnostics[-500:]
        session.commit()

    if pending:
        chunks_total += _persist_chunk_batch(session, run, target, pending)
    if chunks_total == 0:
        detail = diagnostics[0]["message"] if diagnostics else "no searchable chunks were created"
        raise ValueError(f"index contains no searchable chunks: {detail}")

    run.status = "completed"
    run.progress = 100
    run.chunks_total = chunks_total
    run.error = None
    run.diagnostics = diagnostics[-500:]
    run.embedding_model_revision = target.model_id
    run.finished_at = datetime.now(UTC)
    project_index.active_run_id = run.id
    latest_snapshot_matches = session.execute(
        text(
            "SELECT latest.content_hash = built.content_hash "
            "FROM source_snapshots AS latest, source_snapshots AS built "
            "WHERE latest.source_id = :source_id AND latest.source_revision->>'scope' = :scope "
            "AND built.id = :snapshot_id "
            "ORDER BY latest.id DESC LIMIT 1"
        ),
        {
            "source_id": project_index.source_id,
            "scope": project_index.index_type,
            "snapshot_id": run.snapshot_id,
        },
    ).scalar_one_or_none()
    project_index.status = "completed" if latest_snapshot_matches is True else "stale"
    project_index.updated_at = datetime.now(UTC)
    session.commit()


def _parse_file(
    index_type: str,
    snapshot_file_id: int,
    path: str,
    branch: str,
    content_hash: str,
    content: bytes,
    metadata: dict[str, Any],
) -> tuple[list[ChunkPayload], str | None]:
    if index_type == "code":
        code_result = chunk_code_file(
            path=path,
            content=content,
            content_hash=content_hash,
            branch=branch,
            metadata=metadata,
        )
        return [
            ChunkPayload(
                snapshot_file_id,
                chunk.content_hash,
                chunk.path,
                chunk.branch,
                chunk.start_line,
                chunk.end_line,
                chunk.symbol,
                chunk.content,
                f"{chunk.path} {chunk.language} {chunk.symbol}\n{chunk.content}",
                {**chunk.metadata, "language": chunk.language},
            )
            for chunk in code_result.chunks
        ], code_result.diagnostic
    if index_type == "documentation":
        document_result = chunk_document_file(
            path=path,
            content=content,
            content_hash=content_hash,
            metadata=metadata,
        )
        return [
            ChunkPayload(
                snapshot_file_id,
                chunk.content_hash,
                chunk.path,
                branch,
                chunk.start_line,
                chunk.end_line,
                None,
                chunk.content,
                f"{chunk.path} {chunk.section}\n{chunk.content}",
                {**chunk.metadata, "section": chunk.section},
            )
            for chunk in document_result.chunks
        ], document_result.diagnostic
    if index_type == "user_flow":
        if path.lower().endswith(".json"):
            flows = parse_approved_flows(content)
            return [
                ChunkPayload(
                    snapshot_file_id,
                    content_hash,
                    path,
                    branch,
                    None,
                    None,
                    flow.title,
                    render_flow_for_search(flow),
                    render_flow_for_search(flow),
                    {**flow.model_dump(mode="json"), "scope": "user_flow"},
                )
                for flow in flows
            ], None
        document_result = chunk_document_file(
            path=path,
            content=content,
            content_hash=content_hash,
            metadata={**metadata, "scope": "user_flow"},
        )
        return [
            ChunkPayload(
                snapshot_file_id,
                chunk.content_hash,
                chunk.path,
                branch,
                chunk.start_line,
                chunk.end_line,
                chunk.section,
                chunk.content,
                f"{chunk.path} {chunk.section}\n{chunk.content}",
                {**chunk.metadata, "scope": "user_flow"},
            )
            for chunk in document_result.chunks
        ], document_result.diagnostic
    raise ValueError("unsupported index type")


def _persist_chunk_batch(
    session: Session,
    run: IndexRun,
    target: EmbeddingTarget,
    batch: list[ChunkPayload],
) -> int:
    vectors = embed_texts(
        target.provider_type,
        target.base_url,
        target.model_id,
        [chunk.embedding_text for chunk in batch],
        get_settings().provider_request_timeout_seconds,
        target.api_key,
    )
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        raise ValueError("embedding provider returned inconsistent vector dimensions")
    if run.embedding_dimensions is not None and run.embedding_dimensions != dimensions:
        raise ValueError("embedding dimensions changed during indexing")
    run.embedding_dimensions = dimensions
    session.add_all(
        [
            IndexChunk(
                run_id=run.id,
                snapshot_file_id=chunk.snapshot_file_id,
                content_hash=chunk.content_hash,
                path=chunk.path,
                branch=chunk.branch,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                symbol=chunk.symbol,
                content=chunk.content,
                embedding=vector,
                metadata_json=chunk.metadata,
            )
            for chunk, vector in zip(batch, vectors, strict=True)
        ]
    )
    session.flush()
    return len(batch)


def _embedding_target(
    session: Session, model_id: int | None, settings: Settings
) -> EmbeddingTarget:
    if model_id is None:
        raise ValueError("select a local embedding model in project settings first")
    credential_sql = (
        "pgp_sym_decrypt(connection.credential_ciphertext, :secrets_key)"
        if settings.model_secrets_key
        else "NULL"
    )
    query = text(
        "SELECT model.provider_model_id, model.status, connection.provider_type, "
        "connection.base_url, "
        f"CASE WHEN connection.credential_ciphertext IS NULL THEN NULL ELSE {credential_sql} END "
        "AS api_key "
        "FROM workspace_models AS model "
        "JOIN model_provider_connections AS connection "
        "ON connection.id = model.provider_connection_id WHERE model.id = :model_id"
    )
    params: dict[str, Any] = {"model_id": model_id}
    if settings.model_secrets_key:
        params["secrets_key"] = settings.model_secrets_key
    row = session.execute(query, params).one_or_none()
    if row is None:
        raise ValueError("selected embedding model is no longer available")
    provider_type = str(row.provider_type)
    if provider_type not in {"ollama", "freetoken"}:
        raise ValueError("indexing source code and project files requires a local embedding model")
    if str(row.status) not in {"available", "installed"}:
        raise ValueError("selected indexing model is not ready")
    return EmbeddingTarget(
        provider_type=provider_type,
        base_url=str(row.base_url),
        model_id=str(row.provider_model_id),
        api_key=str(row.api_key) if row.api_key is not None else None,
    )


def _human_index_error(error: Exception) -> str:
    message = str(error).strip()
    if message:
        return message[:1000]
    return "indexing failed; retry the operation"


run_project_index_task: Any = celery_app.task(name="vibesolver.indexing.run_project_index")(
    run_project_index
)
