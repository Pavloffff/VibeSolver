from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapter.repositories.tickets import TicketSqlRepository


async def _source_id(db_engine) -> int:
    async with db_engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO sources (type, name, config) "
                "VALUES ('git', 'tickets repo', CAST(:config AS jsonb)) RETURNING id"
            ),
            {"config": '{"url":"https://github.com/x/y.git"}'},
        )
        return int(result.scalar_one())


async def test_ticket_roundtrip_and_append_only_steps(db_engine, clean_database: None) -> None:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    source_id = await _source_id(db_engine)
    async with factory() as session:
        repository = TicketSqlRepository(session)
        ticket = await repository.create(source_id, "Ошибка входа", "Не пускает в админку")

        assert ticket.status == "new"
        assert ticket.title == "Ошибка входа"

        updated = await repository.update_result(
            ticket.id,
            "answered",
            triage={"category": "auth", "severity": "high"},
            answer="Сбросьте пароль",
            citations=[{"source_ref": "run:1:a.py:10", "path": "a.py"}],
        )
        assert updated is not None
        assert updated.status == "answered"
        assert updated.triage == {"category": "auth", "severity": "high"}
        assert updated.citations == [{"source_ref": "run:1:a.py:10", "path": "a.py"}]

        first = await repository.add_step(
            ticket.id, "triage", {"q": 1}, {"category": "auth"}, model_id=3, duration_ms=12
        )
        await repository.add_step(
            ticket.id, "resolve", {}, {"decision": "answer"}, model_id=3, duration_ms=45
        )
        steps = await repository.list_steps(ticket.id)
        assert [step.step for step in steps] == ["triage", "resolve"]
        assert steps[0].input_data == {"q": 1}
        assert steps[0].duration_ms == 12
        assert steps[0].tokens_in is None
        await repository.add_step(
            ticket.id,
            "triage",
            {},
            {},
            model_id=3,
            duration_ms=1,
            tokens_in=10,
            tokens_out=5,
            cost_usd=0.001,
        )
        assert first.ticket_id == ticket.id

        stats = await repository.stats(source_id)
        assert stats.total == 1
        assert stats.by_status == {
            "new": 0,
            "running": 0,
            "answered": 1,
            "escalated": 0,
            "failed": 0,
        }
        assert stats.completed == 1
        assert stats.autoresolve_rate == 1
        assert stats.tokens_in == 10
        assert stats.tokens_out == 5
        assert stats.cost_usd == 0.001
        assert stats.avg_cost_usd == 0.001
        assert stats.avg_tokens_per_ticket == 15

        listed = await repository.list_for_source(source_id)
        assert [item.id for item in listed] == [ticket.id]
        assert await repository.get(ticket.id) is not None


async def test_ticket_stats_empty_source(db_engine, clean_database: None) -> None:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    source_id = await _source_id(db_engine)
    async with factory() as session:
        stats = await TicketSqlRepository(session).stats(source_id)
    assert stats.total == 0
    assert stats.completed == 0
    assert stats.autoresolve_rate == 0
    assert stats.avg_cost_usd is None
    assert stats.avg_tokens_per_ticket == 0
