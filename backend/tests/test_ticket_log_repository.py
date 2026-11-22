from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapter.repositories.ticket_logs import TicketLogSqlRepository


async def _ticket_ids(db_engine) -> tuple[int, int, int]:
    async with db_engine.begin() as connection:
        source = await connection.execute(
            text("INSERT INTO sources (type, name, config) VALUES ('git', 'logs repo', '{}'::jsonb) RETURNING id")
        )
        source_id = int(source.scalar_one())
        result = await connection.execute(
            text(
                "INSERT INTO tickets (source_id, title, description) VALUES "
                "(:source_id, 'first', 'first issue description'), "
                "(:source_id, 'second', 'second issue description') RETURNING id"
            ),
            {"source_id": source_id},
        )
        first, second = [int(row.id) for row in result.all()]
    return source_id, first, second


async def test_ticket_log_attachments_are_scoped_to_their_ticket(
    db_engine, clean_database: None
) -> None:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    source_id, first_ticket, second_ticket = await _ticket_ids(db_engine)

    async with factory() as session:
        repository = TicketLogSqlRepository(session)
        first = await repository.create_attachment(
            source_id, first_ticket, "first.zip", "ticket-logs/first.zip", 100
        )
        second = await repository.create_attachment(
            source_id, second_ticket, "second.zip", "ticket-logs/second.zip", 200
        )
        listed = await repository.list_attachments(source_id, first_ticket)
        assert [item.id for item in listed] == [first.id]
        assert listed[0].filename == "first.zip"
        assert listed[0].status == "queued"
        assert await repository.get_attachment(source_id, first_ticket, second.id) is None


async def test_attachment_status_can_be_updated(db_engine, clean_database: None) -> None:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    source_id, ticket_id, _ = await _ticket_ids(db_engine)

    async with factory() as session:
        repository = TicketLogSqlRepository(session)
        attachment = await repository.create_attachment(
            source_id, ticket_id, "first.zip", "ticket-logs/first.zip", 100
        )
        updated = await repository.update_status(attachment.id, "ready", None)

    assert updated is not None
    assert updated.status == "ready"
