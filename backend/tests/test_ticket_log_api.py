from unittest.mock import Mock

from httpx import AsyncClient
from sqlalchemy import text

from app.adapter.config import get_settings


async def _create_ticket(db_engine) -> int:
    async with db_engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO sources (type, name, config) VALUES ('git', 'logs api', '{}'::jsonb) RETURNING id"
            )
        )
        source_id = int(result.scalar_one())
        result = await connection.execute(
            text(
                "INSERT INTO tickets (source_id, title, description) "
                "VALUES (:source_id, 'Issue', 'An issue with enough details') RETURNING id"
            ),
            {"source_id": source_id},
        )
        return int(result.scalar_one())


async def test_upload_and_list_ticket_log_attachment(
    api_client: AsyncClient, db_engine, clean_database: None, monkeypatch
) -> None:
    from app.adapter import ticket_log_storage
    from app.handler.routes import tickets

    ticket_id = await _create_ticket(db_engine)
    other_ticket_id = await _create_ticket(db_engine)
    fake_s3 = Mock()
    queued = Mock()
    monkeypatch.setattr(ticket_log_storage, "make_s3_client", lambda settings: fake_s3)
    monkeypatch.setattr(ticket_log_storage, "ensure_bucket", lambda client, bucket: None)
    monkeypatch.setattr(tickets.run_ticket_log_attachment, "delay", queued)

    response = await api_client.post(
        f"/api/v1/tickets/{ticket_id}/log-attachments",
        files={"file": ("incident.zip", b"PK\x03\x04log data", "application/zip")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "incident.zip"
    assert body["size_bytes"] == 12
    assert body["status"] == "queued"
    assert "storage_key" not in body
    queued.assert_called_once_with(body["id"])
    fake_s3.put_object.assert_called_once()

    listed = await api_client.get(f"/api/v1/tickets/{ticket_id}/log-attachments")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]

    other_ticket_list = await api_client.get(f"/api/v1/tickets/{other_ticket_id}/log-attachments")
    assert other_ticket_list.status_code == 200
    assert other_ticket_list.json() == []


async def test_log_upload_rejects_unmatched_signature(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    ticket_id = await _create_ticket(db_engine)

    response = await api_client.post(
        f"/api/v1/tickets/{ticket_id}/log-attachments",
        files={"file": ("incident.zip", b"not a zip", "application/zip")},
    )

    assert response.status_code == 422
    assert "matching .zip or .tar.gz" in response.json()["detail"]


async def test_failed_log_attachment_can_be_retried(
    api_client: AsyncClient, db_engine, clean_database: None, monkeypatch
) -> None:
    from app.handler.routes import tickets

    ticket_id = await _create_ticket(db_engine)
    async with db_engine.begin() as connection:
        row = await connection.execute(
            text(
                "INSERT INTO ticket_log_attachments "
                "(source_id, ticket_id, filename, storage_key, size_bytes, status) "
                "SELECT source_id, id, 'logs.zip', 'logs/retry.zip', 12, 'failed' "
                "FROM tickets WHERE id = :ticket_id RETURNING id"
            ),
            {"ticket_id": ticket_id},
        )
        attachment_id = int(row.scalar_one())
    queued = Mock()
    monkeypatch.setattr(tickets.run_ticket_log_attachment, "delay", queued)

    response = await api_client.post(
        f"/api/v1/tickets/{ticket_id}/log-attachments/{attachment_id}/retry"
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    queued.assert_called_once_with(attachment_id)


async def test_log_attachment_can_be_deleted_from_its_ticket(
    api_client: AsyncClient, db_engine, clean_database: None, monkeypatch
) -> None:
    from app.adapter import ticket_log_storage

    ticket_id = await _create_ticket(db_engine)
    async with db_engine.begin() as connection:
        row = await connection.execute(
            text(
                "INSERT INTO ticket_log_attachments "
                "(source_id, ticket_id, filename, storage_key, size_bytes, status) "
                "SELECT source_id, id, 'logs.zip', 'logs/delete.zip', 12, 'ready' "
                "FROM tickets WHERE id = :ticket_id RETURNING id"
            ),
            {"ticket_id": ticket_id},
        )
        attachment_id = int(row.scalar_one())
    fake_s3 = Mock()
    monkeypatch.setattr(ticket_log_storage, "make_s3_client", lambda settings: fake_s3)
    monkeypatch.setattr(ticket_log_storage, "ensure_bucket", lambda client, bucket: None)

    response = await api_client.delete(
        f"/api/v1/tickets/{ticket_id}/log-attachments/{attachment_id}"
    )

    assert response.status_code == 204
    fake_s3.delete_object.assert_called_once_with(
        Bucket=get_settings().s3_bucket_raw, Key="logs/delete.zip"
    )
    async with db_engine.begin() as connection:
        remaining = await connection.execute(
            text("SELECT count(*) FROM ticket_log_attachments WHERE id = :id"),
            {"id": attachment_id},
        )
    assert int(remaining.scalar_one()) == 0


async def test_ticket_run_is_blocked_while_log_attachment_is_queued(
    api_client: AsyncClient, db_engine, clean_database: None, monkeypatch
) -> None:
    from app.handler.routes import tickets

    ticket_id = await _create_ticket(db_engine)
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO ticket_log_attachments "
                "(source_id, ticket_id, filename, storage_key, size_bytes, status) "
                "SELECT source_id, id, 'logs.zip', 'logs/queued.zip', 12, 'queued' "
                "FROM tickets WHERE id = :ticket_id"
            ),
            {"ticket_id": ticket_id},
        )
    monkeypatch.setattr(
        tickets,
        "build_ticket_usecase",
        lambda session: (_ for _ in ()).throw(AssertionError("agent must not start")),
    )

    response = await api_client.post(f"/api/v1/tickets/{ticket_id}/run", json={"profile_id": 1})

    assert response.status_code == 409
    assert "log archive" in response.json()["detail"].lower()


async def test_ticket_run_is_blocked_when_log_attachment_failed(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    ticket_id = await _create_ticket(db_engine)
    async with db_engine.begin() as connection:
        row = await connection.execute(
            text("SELECT source_id FROM tickets WHERE id = :id"), {"id": ticket_id}
        )
        await connection.execute(
            text(
                "INSERT INTO ticket_log_attachments "
                "(source_id, ticket_id, filename, storage_key, size_bytes, status, error) "
                "VALUES (:source_id, :ticket_id, 'logs.zip', 'logs/failed-gate.zip', 12, 'failed', 'bad zip')"
            ),
            {"source_id": int(row.scalar_one()), "ticket_id": ticket_id},
        )

    response = await api_client.post(f"/api/v1/tickets/{ticket_id}/run", json={"profile_id": 1})

    assert response.status_code == 409
    assert "retry or remove" in response.json()["detail"].lower()


async def test_ticket_list_reports_unready_log_attachments(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    ticket_id = await _create_ticket(db_engine)
    async with db_engine.begin() as connection:
        row = await connection.execute(
            text("SELECT source_id FROM tickets WHERE id = :id"), {"id": ticket_id}
        )
        source_id = int(row.scalar_one())
        await connection.execute(
            text(
                "INSERT INTO ticket_log_attachments "
                "(source_id, ticket_id, filename, storage_key, size_bytes, status) "
                "VALUES (:source_id, :ticket_id, 'logs.zip', 'logs/list-pending.zip', 12, 'processing')"
            ),
            {"source_id": source_id, "ticket_id": ticket_id},
        )

    response = await api_client.get(f"/api/v1/sources/{source_id}/tickets")

    assert response.status_code == 200
    assert response.json()[0]["has_unready_log_attachments"] is True
