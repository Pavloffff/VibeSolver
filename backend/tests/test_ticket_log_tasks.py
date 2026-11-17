from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.adapter.config import Settings
from app.adapter.db import to_sync_dsn
from app.adapter.indexing_tasks import EmbeddingTarget
from app.usecase.ticket_logs import LogChunk, LogExtraction


async def test_failed_reindex_preserves_previous_log_chunks(
    db_engine, clean_database: None, test_database_dsn: str, monkeypatch
) -> None:
    from app.adapter import ticket_log_tasks

    async with db_engine.begin() as connection:
        source = await connection.execute(
            text(
                "INSERT INTO sources (type, name, config) "
                "VALUES ('git', 'worker test', '{}'::jsonb) RETURNING id"
            )
        )
        source_id = int(source.scalar_one())
        ticket = await connection.execute(
            text(
                "INSERT INTO tickets (source_id, title, description) "
                "VALUES (:source_id, 'worker test', 'logs worker test') RETURNING id"
            ),
            {"source_id": source_id},
        )
        ticket_id = int(ticket.scalar_one())
        attachment = await connection.execute(
            text(
                "INSERT INTO ticket_log_attachments "
                "(source_id, ticket_id, filename, storage_key, size_bytes, status) "
                "VALUES (:source_id, :ticket_id, 'logs.zip', 'logs/worker.zip', 12, 'failed') "
                "RETURNING id"
            ),
            {"source_id": source_id, "ticket_id": ticket_id},
        )
        attachment_id = int(attachment.scalar_one())
        await connection.execute(
            text(
                "INSERT INTO ticket_log_chunks "
                "(attachment_id, source_id, ticket_id, path, start_line, end_line, content) "
                "VALUES (:attachment_id, :source_id, :ticket_id, 'server.log', 1, 1, 'old evidence')"
            ),
            {
                "attachment_id": attachment_id,
                "source_id": source_id,
                "ticket_id": ticket_id,
            },
        )
        provider = await connection.execute(
            text(
                "INSERT INTO model_provider_connections (provider_type, name, base_url) "
                "VALUES ('ollama', 'worker test', 'http://localhost:11434') RETURNING id"
            )
        )
        provider_id = int(provider.scalar_one())
        model = await connection.execute(
            text(
                "INSERT INTO workspace_models "
                "(provider_connection_id, provider_model_id, display_name, status) "
                "VALUES (:provider_id, 'embedding:test', 'Embedding test', 'available') "
                "RETURNING id"
            ),
            {"provider_id": provider_id},
        )
        model_id = int(model.scalar_one())
        await connection.execute(
            text(
                "INSERT INTO project_model_assignments (source_id, role, model_id) "
                "VALUES (:source_id, 'indexing', :model_id)"
            ),
            {"source_id": source_id, "model_id": model_id},
        )

    sync_engine = create_engine(to_sync_dsn(test_database_dsn))
    factory = sessionmaker(bind=sync_engine, expire_on_commit=False)
    monkeypatch.setattr(ticket_log_tasks, "get_index_session_factory", lambda: factory)
    monkeypatch.setattr(
        ticket_log_tasks,
        "get_settings",
        lambda: Settings(database_url=test_database_dsn),
    )
    fake_s3 = Mock()
    fake_s3.get_object.return_value = {"Body": b"archive"}
    monkeypatch.setattr(ticket_log_tasks, "make_s3_client", lambda settings: fake_s3)
    monkeypatch.setattr(
        ticket_log_tasks,
        "extract_log_archive",
        lambda filename, data, max_bytes: LogExtraction(
            [LogChunk("server.log", 1, 1, None, "utf-8", "new evidence")], []
        ),
    )
    monkeypatch.setattr(
        ticket_log_tasks,
        "embed_texts",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    try:
        with pytest.raises(RuntimeError, match="provider unavailable"):
            ticket_log_tasks._run_ticket_log_attachment(attachment_id)
    finally:
        sync_engine.dispose()

    async with db_engine.begin() as connection:
        chunks = await connection.execute(
            text("SELECT content FROM ticket_log_chunks WHERE attachment_id = :attachment_id"),
            {"attachment_id": attachment_id},
        )
        attachment_state = await connection.execute(
            text("SELECT status FROM ticket_log_attachments WHERE id = :id"),
            {"id": attachment_id},
        )

    assert [row.content for row in chunks.all()] == ["old evidence"]
    assert attachment_state.scalar_one() == "failed"


def test_log_embeddings_are_requested_in_bounded_batches(monkeypatch) -> None:
    from app.adapter import ticket_log_tasks

    requested_sizes: list[int] = []

    def embed(provider, base_url, model_id, texts, timeout, api_key):
        requested_sizes.append(len(texts))
        return [[1.0] for _ in texts]

    monkeypatch.setattr(ticket_log_tasks, "embed_texts", embed)
    chunks = [
        LogChunk("server.log", index, index, None, "utf-8", f"line {index}") for index in range(50)
    ]
    pairs = list(
        ticket_log_tasks._embed_log_chunks(
            chunks,
            EmbeddingTarget("ollama", "http://localhost", "model", None),
            Settings(),
        )
    )

    assert len(pairs) == 50
    assert requested_sizes == [48, 2]
