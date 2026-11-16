# Дизайн: каскад моделей конвейера обращений

## Роли и маршрутизация

`PROJECT_MODEL_ROLES += {"ticket_triage": "chat", "ticket_resolution_cheap": "chat"}`. Разрешение моделей в `TicketAgentUsecase`:

- `resolver_strong` = роль `ticket_resolution` (обязательна, как сейчас);
- `triage_model` = роль `ticket_triage`, иначе `resolver_strong`;
- `cheap_model` = роль `ticket_resolution_cheap`, иначе `None`.

`TriageResult` расширяется полем `complexity: Literal["simple","standard","hard"]` (строгая валидация значений). Правило маршрутизации решателя — чистая функция:

```
resolver_model = cheap_model if (cheap_model and triage.complexity == "simple") else strong
```

Причина попадает в output шага `resolve`: `{"routing": {"complexity": ..., "tier": "cheap"|"strong", "reason": ...}}`. Триаж-промпт дополняется инструкцией оценивать complexity по правилу: известная ошибка/вопрос по документации → simple; воспроизводимый баг → standard; подозрение на дефект кода/инфраструктуры, многосистемный кейс → hard.

## Usage и стоимость

- `MaterialGenerationGateway` расширяется методом `generate_json_with_usage(...) -> GeneratedJson{text, input_tokens, output_tokens}`; `MaterialGenerationAdapter` реализует его поверх новой функции `complete_json_with_usage` в `providers.py` (все chat-адаптеры рефакторятся с внутреннего «вернуть текст» на «вернуть (текст, usage-словарь)»; `complete_json` остаётся оболочкой для совместимости — генерация материалов не меняется).
- usage берётся из стандартного поля `usage: {input_tokens|prompt_tokens, output_tokens|completion_tokens}` ответов OpenAI-совместимых/Anthropic/Ollama (у Ollama `/api/chat` — `prompt_eval_count`/`eval_count`; маппинг в адаптере).
- Миграция `00006_ticket_step_usage.sql`: `ALTER TABLE ticket_steps ADD COLUMN tokens_in INT, ADD COLUMN tokens_out INT, ADD COLUMN cost_usd NUMERIC(12,6)`.
- Стоимость: `workspace_models.metadata.pricing` в формате OpenRouter — `{"prompt": "<$ за 1 токен>", "completion": "<...>"}` (строки!). cost = in×prompt + out×completion; отсутствие поля или нечисловые значения → cost не считается (None). Функция цены — чистая, юнит-тесты на парсинг.

## Метрики

`GET /api/v1/sources/{id}/tickets/stats` → `{total, by_status: {...}, completed, autoresolve_rate, tokens_in, tokens_out, cost_usd, avg_cost_usd, avg_tokens_per_ticket}`. Агрегация SQL-джойном tickets×ticket_steps (один запрос) в `TicketSqlRepository.stats()`. Считаются только завершённые (answered/escalated/failed) для честного среднего. UI: компактная карточка над списком обращений (автоварешения %, средний $/тикет, токены).

## Эксперимент single vs cascade

Ручной протокол в `docs/ticket-agent.md`: прогнать один и тот же набор ~10 тикетов на конфигурации A (все шаги на сильной модели) и B (triage+cheap на дешёвой, strong только для standard/hard), зафиксировать stats-эндпоинтом. Скрипты не пишем — метрики уже в API, протокол документируем.

## Совместимость

- Контракт `complexity` — новое обязательное поле выхода триажа: старые ответы модели без него провалят валидацию и уйдут в repair; допустимо (repair-механизм есть). Альтернатива со default="standard" отвергнута: молча неверная маршрутизация хуже явного повтора.
- `ModelSelectionOut` расширяется двумя nullable-полями; фронтенд-типы соответственно.
