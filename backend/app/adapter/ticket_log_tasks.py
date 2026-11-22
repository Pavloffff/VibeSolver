import json
from collections.abc import Iterator
from typing import Any

from sqlalchemy import text

from app.adapter.celery_app import celery_app
from app.adapter.config import Settings, get_settings
from app.adapter.indexing_tasks import (
    EmbeddingTarget,
    _embedding_target,
    get_index_session_factory,
)
from app.adapter.model_providers.providers import embed_texts
from app.adapter.s3 import make_s3_client
from app.usecase.ticket_logs import LogChunk, extract_log_archive

LOG_EMBEDDING_BATCH_SIZE = 48


def _run_ticket_log_attachment(attachment_id: int) -> None:
    settings = get_settings()
    session_factory = get_index_session_factory()
    with session_factory() as session:
        row = session.execute(
            text(
                "SELECT id, source_id, ticket_id, filename, storage_key "
                "FROM ticket_log_attachments WHERE id = :id"
            ),
            {"id": attachment_id},
        ).one_or_none()
        if row is None:
            return
        claimed = session.execute(
            text(
                "UPDATE ticket_log_attachments SET status = 'processing', error = NULL, "
                "updated_at = now() WHERE id = :id AND status IN ('queued', 'failed') "
                "RETURNING id"
            ),
            {"id": attachment_id},
        ).one_or_none()
        if claimed is None:
            session.rollback()
            return
        previous_max_id = session.execute(
            text("SELECT COALESCE(MAX(id), 0) FROM ticket_log_chunks WHERE attachment_id = :id"),
            {"id": attachment_id},
        ).scalar_one()
        session.commit()
        try:
            result = make_s3_client(settings).get_object(
                Bucket=settings.s3_bucket_raw, Key=str(row.storage_key)
            )["Body"]
            archive = result if isinstance(result, bytes) else result.read()
            extraction = extract_log_archive(
                str(row.filename), archive, settings.max_archive_unpacked_bytes
            )
            if not extraction.chunks:
                raise ValueError("archive contains no supported readable log entries")
            model_id = session.execute(
                text(
                    "SELECT model_id FROM project_model_assignments "
                    "WHERE source_id = :source_id AND role = 'indexing'"
                ),
                {"source_id": row.source_id},
            ).scalar_one_or_none()
            if model_id is None:
                raise ValueError("select an embedding model in project settings first")
            target = _embedding_target(session, int(model_id), settings)
            for chunk, vector in _embed_log_chunks(extraction.chunks, target, settings):
                session.execute(
                    text(
                        "INSERT INTO ticket_log_chunks "
                        "(attachment_id, source_id, ticket_id, path, start_line, end_line, "
                        "event_timestamp, content, embedding, metadata_json) "
                        "VALUES (:attachment_id, :source_id, :ticket_id, :path, :start_line, "
                        ":end_line, :event_timestamp, :content, CAST(:embedding AS vector), "
                        "CAST(:metadata AS jsonb))"
                    ),
                    {
                        "attachment_id": attachment_id,
                        "source_id": row.source_id,
                        "ticket_id": row.ticket_id,
                        "path": chunk.path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "event_timestamp": chunk.timestamp,
                        "content": chunk.content,
                        "embedding": _vector_literal(vector),
                        "metadata": json.dumps({"encoding": chunk.encoding}),
                    },
                )
            session.execute(
                text(
                    "DELETE FROM ticket_log_chunks WHERE attachment_id = :id "
                    "AND id <= :previous_max_id"
                ),
                {"id": attachment_id, "previous_max_id": previous_max_id},
            )
            session.execute(
                text(
                    "UPDATE ticket_log_attachments SET status = 'ready', error = NULL, "
                    "embedding_model_id = :model_id, updated_at = now() WHERE id = :id"
                ),
                {"id": attachment_id, "model_id": int(model_id)},
            )
            session.commit()
        except Exception:
            session.rollback()
            session.execute(
                text(
                    "UPDATE ticket_log_attachments SET status = 'failed', error = :error, "
                    "updated_at = now() WHERE id = :id"
                ),
                {
                    "id": attachment_id,
                    "error": (
                        "Не удалось проиндексировать архив логов. Проверьте формат и выбранную "
                        "embedding-модель."
                    )[:1000],
                },
            )
            session.commit()
            raise


def _embed_log_chunks(
    chunks: list[LogChunk], target: EmbeddingTarget, settings: Settings
) -> Iterator[tuple[LogChunk, list[float]]]:
    for start in range(0, len(chunks), LOG_EMBEDDING_BATCH_SIZE):
        batch = chunks[start : start + LOG_EMBEDDING_BATCH_SIZE]
        vectors = embed_texts(
            target.provider_type,
            target.base_url,
            target.model_id,
            [chunk.content for chunk in batch],
            settings.provider_request_timeout_seconds,
            target.api_key,
        )
        if len(vectors) != len(batch):
            raise ValueError("embedding provider returned a different number of vectors")
        yield from zip(batch, vectors, strict=True)


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"


run_ticket_log_attachment: Any = celery_app.task(name="vibesolver.ticket_logs.process_attachment")(
    _run_ticket_log_attachment
)
