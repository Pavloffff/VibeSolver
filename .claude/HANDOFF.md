# HANDOFF — фаза 3 cost-routing В РАБОТЕ (17.11.2026, ночной сеанс)

Фаза 2 запушена (`89bd988`, `d06b2e5`, `5fc399d`, change заархивирован). Фаза 3 `cost-routing` — openspec-change оформлен, скелет имплементации закоммичен как WIP. **Этот файл удали, когда закончишь фазу 3.**

## Контекст

- Правила: `AGENTS.md` + `openspec/AGENTS.md` (TDD, mypy strict, реэкспорт OpenAPI, i18n en/ru/zh, коммит только по явной команде). Команды: `/opsx:*`, `/project-checks`.
- Стратегия: киллер-фича — экономия токенов; метрики **$/тикет** и **% автоварешений**. Фаза 3 = каскад моделей (см. `openspec/changes/cost-routing/proposal.md` + `design.md`).

## ЧТО УЖЕ СДЕЛАНО (в WIP-коммите)

1. **openspec/changes/cost-routing/** — proposal, spec, design, tasks (11 задач).
2. **Миграция `00006_ticket_step_usage.sql`** (tokens_in/tokens_out/cost_usd в ticket_steps). НАКАЧЕНА на запущенный postgres (стек поднят, после тестов — `docker compose down -v`).
3. **Домен**: `TicketStep` + usage-поля, `TicketStats`; протокол `TicketRepository` — `add_step(tokens_in/out, cost_usd)`, `usage_rows(source_id)`; `TicketSqlRepository` реализует оба.
4. **Цены**: `app/usecase/ticket_pricing.py` — `parse_pricing(metadata)` (OpenRouter-формат `pricing.prompt/completion`, строки→Decimal) и `step_cost_usd`. Юнит-тестов НЕТ.
5. **Провайдеры с usage** (`providers.py`): `GenerationUsage` TypedDict, `complete_json_with_usage(...) -> (text, usage)`; все chat-адаптеры (openai-compatible/anthropic/openai/ollama) возвращают кортеж; usage-маппинги `_openai_usage` (input/prompt_tokens, output/completion_tokens), `_anthropic_usage` (input/output_tokens), `_ollama_usage` (prompt_eval_count/eval_count); `complete_json` — оболочка. Тесты `test_cloud_providers.py` ОБНОВЛЕНЫ на кортежи (9 passed на момент коммита).
6. **Шлюз**: `MaterialGenerationGateway.generate_json_with_usage -> GeneratedJson`; адаптер реализует. `complete_json` генерации материалов не тронут.
7. **Роли**: `PROJECT_MODEL_ROLES += ticket_triage, ticket_resolution_cheap` (обе chat).
8. **Конвейер** (`ticket_agent.py`): `TriageResult.complexity` (simple|standard|hard, strict) + правила в промпте; `ModelTarget{model, credentials, pricing}` / `PipelineTargets{triage, strong, cheap}`; `_resolve_models` с деградацией (нет triage → strong; cheap опционален); чистая функция `resolver_target(triage, targets)` (simple+cheap → cheap); шаги triage/resolve пишут usage+cost; repair-вызовы суммируются в usage; routing-причина в output шага resolve. **mypy strict чистый.**

## ИЗВЕСТНО СЛОМАНО / НЕ СДЕЛАНО (продолжать отсюда)

1. **`tests/test_ticket_agent.py` (13 тестов) ПАДАЮТ** — ожидаемо: фикстура `TRIAGE_JSON` без поля `complexity`; `FakeGateway` без метода `generate_json_with_usage`. Фикс: добавить `"complexity": "standard"` в фикстуру + сделать у фейка `generate_json_with_usage` (оборачивать очередь ответов в `GeneratedJson`). Новых тестов на usage/routing/цены нет (TDD: сначала тесты).
2. **Селекции НЕ расширены** (задача 6 частично): `ModelSelectionOut`/роуты `model_providers.py` и фронтенд-типы не знают `ticket_triage`/`ticket_resolution_cheap`.
3. **Тесты по tasks.md**: №1 (repo usage), №2 (pricing), №3 (usage-маппинги провайдеров), №5 (контракт complexity), №6 (роли+деградация), №7 (все ветки маршрутизации, usage None, цены есть/нет).
4. **Задача 8 не начата**: `TicketSqlRepository.stats()` (или на базе `usage_rows`) + `GET /sources/{id}/tickets/stats` + схемы + OpenAPI реэкспорт + тесты. Ответ по спеке: total, by_status, completed, autoresolve_rate, tokens_in/out, cost_usd, avg_cost_usd, avg_tokens_per_ticket (средние только по завершённым: answered/escalated/failed).
5. **Задача 9 не начата**: UI — три селектора моделей (триаж/решение/дешёвая) в IssuesPage, карточка статистики; типы/клиент/i18n ×3; тесты.
6. **Задача 10 не начата**: `docs/ticket-agent.md` — раздел cost-routing + протокол эксперимента single vs cascade; `docs/running.md`.
7. Отметить сделанное в `openspec/changes/cost-routing/tasks.md`; в конце `/project-checks`, архивация и пуш по подтверждению пользователя.

## Окружение

- Backend: `cd backend && uv run --no-sync ...`; PyPI недоступен из песочницы (`uv add` падает).
- Postgres+seaweed УЖЕ ПОДНЯТЫ, миграции применены (включая 00006). После работы: `docker compose down -v`.
- Команда миграций (если поднимаешь стек заново): `cd backend && for f in migrations/0000*.sql; do sed -n '/^-- +goose Up/,/^-- +goose Down/{/^-- +goose Down/q;p}' "$f" | docker compose -f ../docker-compose.yml exec -T postgres psql -U vibesolver -d vibesolver -v ON_ERROR_STOP=1 -q; done`
- Фронтенд-тесты: `testTimeout=20000` уже в vite.config.ts; падение 1 теста под нагрузкой — прогнать изолированно.
- Общение с пользователем — русский, кратко; решения «по умолчанию» списком вето-точек.
