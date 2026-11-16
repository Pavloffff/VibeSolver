# Дизайн: агентный MVP обработки обращений

## Оркестратор вместо LangGraph

Граф MVP — линейный с одним детерминированным ветвлением (эскалация), поэтому вводить зависимость `langgraph` преждевременно: реестр шагов + цикл с лимитом дают тот же контракт «детерминированные рёбра, Pydantic-выходы, append-only трассировка», не добавляя пакет и не требуя обновления lock-файла. Шаг оформляется протоколом домена:

```
AgentStep = Protocol: name, run(ctx: TicketContext) -> AgentStepResult
TICKET_AGENT_STEPS: реестр [TriageAgent, InvestigatorAgent, ResolverAgent]
```

Миграция на LangGraph — точечная замена цикла, если появятся циклы Fix Writer ↔ Investigator (фаза 4).

## Конвейер

```
TriageAgent      LLM → TriageResult{category, severity, search_queries[1..5], missing_info}
InvestigatorAgent RetrievalUsecase по search_queries (top_k на запрос, дедуп по chunk_id,
                  лимит чанков/символов) → Dossier{chunks c source_ref}
ResolverAgent     LLM → ResolutionResult{decision: answer|escalate, answer?, escalate_reason?, source_refs[]}
```

- Маршрутизация: `escalate` ИЛИ пустое досье ИЛИ все ссылки невалидны → статус `escalated`; иначе `answered`.
- Итерации: один проход (LIMIT=1), повтор — только новым запуском.
- Пустое досье → эскалация «в индексах нет релевантного контента» без вызова Решателя (экономия токенов — первый кирпич cost-направления).
- Выходы LLM — Pydantic strict (`extra="forbid"`), с одним repair-повтором как в генерации материалов.

## Промпты

Реестр `TICKET_AGENT_PROMPTS` (русский язык ответа; цитировать только переданные source_ref; не выдумывать; при неуверенности — escalate). Триаж пишет краткое саммари обращения для трассировки.

## Данные

Миграция `00005_tickets.sql`:

- `tickets(id, source_id FK, title, description, status, triage jsonb, answer text, escalate_reason text, citations jsonb, created_at, updated_at)` + индекс `(source_id, created_at desc)`.
- `ticket_steps(id, ticket_id FK, step, input jsonb, output jsonb, model_id, duration_ms, created_at)` — append-only, без UPDATE/DELETE в коде.
- Статусы — данные реестра `TICKET_STATUSES`, не CHECK (философия расширяемости).

Роль модели: `PROJECT_MODEL_ROLES += {"ticket_resolution": "chat"}`; селектор — существующий PUT selections API + селектор в UI обращений.

## API

- `POST /api/v1/sources/{id}/tickets` {title, description} → 201 TicketOut
- `GET /api/v1/sources/{id}/tickets` → список (id, title, status, created_at)
- `GET /api/v1/tickets/{id}` → TicketOut + steps[]
- `POST /api/v1/tickets/{id}/run` → 200 TicketOut (синхронно, таймаут как у генерации; 409 если running; 422/502 как у генерации)

## UI

IssuesPage (сейчас заглушка): форма создания, список с бейджами статусов, кнопка «Запустить»/«Повторить», результат: ответ с раскрывающимся списком источников (path:line), причина эскалации, трассировка шагов (сворачиваемая), селектор chat-модели (паттерн generation-model-picker). i18n ×3. Поллинг статуса не нужен — запуск синхронный.

## Открытые вопросы (по умолчанию)

- Вложения (логи/скриншоты) — не в MVP; поле description принимает вставленный текст лога.
- Ответ хранится целиком в `tickets.answer`; версионирование ответов — через шаги трассировки.
- Лимиты досье: 12 чанков / 24k символов (как у генерации материалов), вынесены в настройки.
