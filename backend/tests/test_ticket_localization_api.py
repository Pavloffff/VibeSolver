import asyncio
import json
from pathlib import Path
from threading import Event
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.model_provider_entities import ProviderCredentials, WorkspaceModelEntry
from app.domain.repositories.material_generation import GeneratedJson
from app.handler.routes import ticket_localization


@pytest.fixture
async def answered_ticket(git_source_id: int, db_engine: AsyncEngine) -> int:
    async with db_engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO tickets (source_id, title, description, status, answer) "
                "VALUES (:source, 'Legacy ticket', 'Private source description', "
                "'answered', 'Проверьте настройки.') RETURNING id"
            ),
            {"source": git_source_id},
        )
        ticket_id = int(result.scalar_one())
        run = await connection.execute(
            text(
                "INSERT INTO ticket_runs (ticket_id, profile_id, profile_name, enabled, models, "
                "status, finished_at) VALUES (:ticket, 20, 'Original', '{}', '{}', 'answered', now()) "
                "RETURNING id"
            ),
            {"ticket": ticket_id},
        )
        await connection.execute(
            text(
                "INSERT INTO ticket_steps (ticket_id, run_id, step, model_id) "
                "VALUES (:ticket, :run, 'resolve', 41)"
            ),
            {"ticket": ticket_id, "run": int(run.scalar_one())},
        )
    return ticket_id


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock]:
    models = Mock()
    models.get_model = AsyncMock(
        return_value=WorkspaceModelEntry(
            provider_model_id="original-model",
            display_name="Original model",
            capabilities=["chat"],
            id=41,
            provider_connection_id=51,
        )
    )
    models.get_credentials = AsyncMock(
        return_value=ProviderCredentials(51, "ollama", "original", "http://localhost", None)
    )
    gateway = Mock()
    gateway.generate_json_with_usage.return_value = GeneratedJson(
        text=json.dumps(
            {"original_language": "ru", "en": "Check the settings.", "ru": None, "zh": "检查设置。"}
        )
    )
    monkeypatch.setattr(ticket_localization, "ModelProviderSqlRepository", lambda *_: models)
    monkeypatch.setattr(ticket_localization, "MaterialGenerationAdapter", lambda: gateway)
    return models, gateway


async def test_legacy_translation_is_cached_across_concurrent_requests(
    api_client: AsyncClient,
    answered_ticket: int,
    provider: tuple[Mock, Mock],
    db_engine: AsyncEngine,
) -> None:
    url = f"/api/v1/tickets/{answered_ticket}/localize"
    responses = await asyncio.gather(api_client.post(url), api_client.post(url))
    expected = {
        "localized_result": {
            "en": "Check the settings.",
            "ru": "Проверьте настройки.",
            "zh": "检查设置。",
        },
        "english_result": "Check the settings.",
    }
    assert all(
        response.status_code == 200 and response.json() == expected for response in responses
    )
    assert (await api_client.post(url)).json() == expected
    models, gateway = provider
    models.get_model.assert_awaited_once_with(41)
    models.get_credentials.assert_awaited_once_with(51)
    gateway.generate_json_with_usage.assert_called_once()
    args = gateway.generate_json_with_usage.call_args.args
    assert args[1] == "original-model"
    assert json.loads(args[3])["text"] == "Проверьте настройки."
    async with db_engine.connect() as connection:
        result = await connection.execute(
            text("SELECT answer FROM tickets WHERE id = :ticket"), {"ticket": answered_ticket}
        )
        assert result.scalar_one() == "Проверьте настройки."


async def test_legacy_translation_discards_result_if_a_rerun_starts(
    api_client: AsyncClient,
    answered_ticket: int,
    provider: tuple[Mock, Mock],
    db_engine: AsyncEngine,
) -> None:
    _, gateway = provider
    started, release = Event(), Event()

    def delayed_translation(*_args: object) -> GeneratedJson:
        started.set()
        assert release.wait(5), "test did not release the provider"
        return gateway.generate_json_with_usage.return_value

    gateway.generate_json_with_usage.side_effect = delayed_translation
    task = asyncio.create_task(api_client.post(f"/api/v1/tickets/{answered_ticket}/localize"))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        async with db_engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE tickets SET status = 'running', updated_at = now() WHERE id = :ticket"
                ),
                {"ticket": answered_ticket},
            )
    finally:
        release.set()
    response = await task
    assert response.status_code == 200
    assert response.json() == {"localized_result": None, "english_result": None}
    async with db_engine.connect() as connection:
        result = await connection.execute(
            text("SELECT localized_result FROM tickets WHERE id = :ticket"),
            {"ticket": answered_ticket},
        )
        assert result.scalar_one() is None


@pytest.mark.parametrize("english_in_first_response", [True, False])
async def test_legacy_english_result_is_cached_after_unavailable_translations(
    api_client: AsyncClient,
    answered_ticket: int,
    provider: tuple[Mock, Mock],
    db_engine: AsyncEngine,
    english_in_first_response: bool,
) -> None:
    _, gateway = provider
    gateway.generate_json_with_usage.side_effect = [
        GeneratedJson(
            text=json.dumps(
                {
                    "original_language": "ru",
                    "en": "Check the settings."
                    if english_in_first_response
                    else "Проверьте настройки.",
                    "ru": None,
                    "zh": None,
                }
            )
        ),
        GeneratedJson(text='{"en": "Check the settings."}'),
    ]
    url = f"/api/v1/tickets/{answered_ticket}/localize"
    expected = {"localized_result": None, "english_result": "Check the settings."}
    responses = await asyncio.gather(api_client.post(url), api_client.post(url))
    assert all(
        response.status_code == 200 and response.json() == expected for response in responses
    )
    assert (await api_client.post(url)).json() == expected
    assert gateway.generate_json_with_usage.call_count == (1 if english_in_first_response else 2)
    assert all(
        call.args[1] == "original-model" for call in gateway.generate_json_with_usage.call_args_list
    )
    ticket = (await api_client.get(f"/api/v1/tickets/{answered_ticket}")).json()["ticket"]
    assert ticket["answer"] == "Проверьте настройки."
    assert ticket["english_result"] == "Check the settings."
    assert ticket["localized_result"] is None


async def test_english_result_migration_only_backfills_known_english(
    db_engine: AsyncEngine,
) -> None:
    migration_path = (
        Path(__file__).resolve().parents[1] / "migrations" / "00014_english_ticket_results.sql"
    )
    migration = migration_path.read_text(encoding="utf-8").split("-- +goose Down")[0]
    async with db_engine.begin() as connection:
        await connection.execute(
            text("""
            CREATE TEMP TABLE tickets (
                id bigint, status text, answer text, escalate_reason text, localized_result jsonb
            ) ON COMMIT DROP
        """)
        )
        await connection.execute(
            text("""
            CREATE TEMP TABLE ticket_runs (
                id bigint, ticket_id bigint, status text, finished_at timestamptz
            ) ON COMMIT DROP
        """)
        )
        await connection.execute(
            text("""
            CREATE TEMP TABLE ticket_steps (
                run_id bigint, ticket_id bigint, step text, output_json jsonb
            ) ON COMMIT DROP
        """)
        )
        await connection.execute(
            text("""
            INSERT INTO tickets (id, status, answer, escalate_reason, localized_result)
            VALUES (1, 'answered', 'Проверьте настройки.', NULL, NULL),
                   (2, 'answered', 'Check the settings.', NULL, NULL),
                   (3, 'answered', 'Проверьте настройки.', NULL,
                    '{"en":"Check the settings.","ru":"Проверьте настройки.","zh":"检查设置。"}'),
                   (4, 'escalated', NULL, 'New issue needs a different review.', NULL),
                   (5, 'escalated', NULL, 'Check connector state.', NULL)
        """)
        )
        await connection.execute(
            text("""
            INSERT INTO ticket_runs (id, ticket_id, status, finished_at)
            VALUES (2, 2, 'answered', now()), (4, 4, 'escalated', now()),
                   (5, 4, 'escalated', now()), (6, 5, 'escalated', now())
        """)
        )
        await connection.execute(
            text("""
            INSERT INTO ticket_steps (run_id, ticket_id, step, output_json)
            VALUES (2, 2, 'answer', '{"localization_status":"failed"}'),
                   (4, 4, 'escalate', '{"localization_status":"completed"}'),
                   (6, 5, 'escalate', '{"localization_status":"failed"}')
        """)
        )
        for statement in migration.strip().strip(";").split(";"):
            await connection.execute(text(statement))
        english = await connection.scalars(text("SELECT english_result FROM tickets ORDER BY id"))
        assert list(english) == [
            None,
            "Check the settings.",
            "Check the settings.",
            None,
            "Check connector state.",
        ]


async def test_legacy_localization_does_not_publish_untranslated_text_as_english(
    api_client: AsyncClient,
    answered_ticket: int,
    provider: tuple[Mock, Mock],
) -> None:
    _, gateway = provider
    gateway.generate_json_with_usage.side_effect = [
        GeneratedJson(text='{"original_language":"en","en":null,"ru":null,"zh":null}'),
        GeneratedJson(text='{"en":"Проверьте настройки."}'),
    ]
    response = await api_client.post(f"/api/v1/tickets/{answered_ticket}/localize")
    assert response.status_code == 200
    assert response.json() == {"localized_result": None, "english_result": None}
