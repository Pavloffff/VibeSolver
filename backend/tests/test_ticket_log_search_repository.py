from sqlalchemy import text

from app.adapter.repositories.ticket_log_search import TicketLogSearchSqlRepository


async def test_ticket_log_search_is_scoped_to_ticket_and_ready_attachments(
    db_engine, clean_database: None
) -> None:
    async with db_engine.begin() as connection:
        source = await connection.execute(
            text(
                "INSERT INTO sources (type, name, config) "
                "VALUES ('git', 'log search', '{}'::jsonb) RETURNING id"
            )
        )
        source_id = int(source.scalar_one())
        tickets = await connection.execute(
            text(
                "INSERT INTO tickets (source_id, title, description) VALUES "
                "(:source_id, 'first', 'first issue'), (:source_id, 'second', 'second issue') "
                "RETURNING id"
            ),
            {"source_id": source_id},
        )
        first_ticket, second_ticket = [int(row.id) for row in tickets.all()]
        provider = await connection.execute(
            text(
                "INSERT INTO model_provider_connections (provider_type, name, base_url) "
                "VALUES ('ollama', 'search test', 'http://localhost:11434') RETURNING id"
            )
        )
        provider_id = int(provider.scalar_one())
        models = await connection.execute(
            text(
                "INSERT INTO workspace_models "
                "(provider_connection_id, provider_model_id, display_name, status) VALUES "
                "(:provider_id, 'search:test:v1', 'Search Test 1', 'available'), "
                "(:provider_id, 'search:test:v2', 'Search Test 2', 'available') RETURNING id"
            ),
            {"provider_id": provider_id},
        )
        model_ids = [int(row.id) for row in models.all()]
        attachments = await connection.execute(
            text(
                "INSERT INTO ticket_log_attachments "
                "(source_id, ticket_id, filename, storage_key, size_bytes, status, embedding_model_id) VALUES "
                "(:source_id, :first, 'first.zip', 'search/first.zip', 12, 'ready', :model1), "
                "(:source_id, :first, 'othermodel.zip', 'search/othermodel.zip', 12, 'ready', :model2), "
                "(:source_id, :second, 'second.zip', 'search/second.zip', 12, 'ready', :model1), "
                "(:source_id, :first, 'queued.zip', 'search/queued.zip', 12, 'processing', :model1) "
                "RETURNING id, ticket_id, status, embedding_model_id"
            ),
            {
                "source_id": source_id,
                "first": first_ticket,
                "second": second_ticket,
                "model1": model_ids[0],
                "model2": model_ids[1],
            },
        )
        attachment_ids = {
            (int(row.ticket_id), str(row.status), int(row.embedding_model_id)): int(row.id)
            for row in attachments.all()
        }
        await connection.execute(
            text(
                "INSERT INTO ticket_log_chunks "
                "(attachment_id, source_id, ticket_id, path, start_line, end_line, content, embedding) "
                "VALUES "
                "(:first_attachment, :source_id, :first, 'first.log', 1, 2, 'OOM killer event', "
                "CAST('[1,0]' AS vector)), "
                "(:other_model_attachment, :source_id, :first, 'othermodel.log', 1, 2, 'OOM killer event', "
                "CAST('[1,0]' AS vector)), "
                "(:second_attachment, :source_id, :second, 'second.log', 1, 2, 'OOM killer event', "
                "CAST('[1,0]' AS vector)), "
                "(:queued_attachment, :source_id, :first, 'queued.log', 1, 2, 'OOM killer event', "
                "CAST('[1,0]' AS vector))"
            ),
            {
                "first_attachment": attachment_ids[(first_ticket, "ready", model_ids[0])],
                "other_model_attachment": attachment_ids[(first_ticket, "ready", model_ids[1])],
                "second_attachment": attachment_ids[(second_ticket, "ready", model_ids[0])],
                "queued_attachment": attachment_ids[(first_ticket, "processing", model_ids[0])],
                "source_id": source_id,
                "first": first_ticket,
                "second": second_ticket,
            },
        )

    async with db_engine.connect() as connection:
        repository = TicketLogSearchSqlRepository(connection)
        lexical = await repository.search_lexical(source_id, first_ticket, "OOM killer", limit=10)
        dense = await repository.search_dense(
            source_id, first_ticket, model_ids[0], [1.0, 0.0], limit=10
        )

    assert [item.path for item in lexical] == ["first.log", "othermodel.log"]
    assert [item.path for item in dense] == ["first.log"]
    assert lexical[0].ticket_id == first_ticket
    assert lexical[0].attachment_id == attachment_ids[(first_ticket, "ready", model_ids[0])]
