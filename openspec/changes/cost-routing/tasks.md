# Задачи: каскад моделей конвейера обращений

- [ ] 1. Миграция `00006_ticket_step_usage.sql`: `tokens_in`, `tokens_out`, `cost_usd` в `ticket_steps`; протокол репозитория и SQL-слой расширяются параметрами add_step; тесты репозитория.
- [ ] 2. Функция цены: парсинг `metadata.pricing` (OpenRouter-формат, строки→Decimal), расчёт стоимости; чистые юнит-тесты (валидные цены, отсутствие, мусор).
- [ ] 3. `complete_json_with_usage` в `providers.py`: все chat-адаптеры (openai-compatible, anthropic, ollama) возвращают usage (маппинги полей каждого провайдера), `complete_json` — оболочка; юнит-тесты на извлечение usage из ответов.
- [ ] 4. `MaterialGenerationGateway.generate_json_with_usage` + адаптер; генерация материалов не меняется (существующие тесты зелёные).
- [ ] 5. `TriageResult.complexity` (simple|standard|hard, strict) + обновление промпта триажа правилами оценки; тесты контракта.
- [ ] 6. Роли `ticket_triage` и `ticket_resolution_cheap` в `PROJECT_MODEL_ROLES`, схемы/роуты selections, разрешение моделей с деградацией к `ticket_resolution`; тесты.
- [ ] 7. Маршрутизация в `TicketAgentUsecase`: чистая функция выбора модели решателя, причина в трассировке, usage+cost в шагах (repair-вызовы тоже учитываются); тесты всех веток (cheap выбран/нет, simple/standard/hard, usage None, цены есть/нет).
- [ ] 8. `TicketSqlRepository.stats()` + `GET /sources/{id}/tickets/stats` + схемы + OpenAPI реэкспорт + тесты маршрута (в т.ч. пустой проект).
- [ ] 9. Фронтенд: три селектора моделей (триаж/решение/дешёвая) с пометками, карточка статистики (автоварешения, $/тикет, токены), типы/клиент/i18n ×3; тесты IssuesPage.
- [ ] 10. Доки: `docs/ticket-agent.md` — раздел cost-routing + протокол эксперимента single vs cascade; `docs/running.md` — переменные и роли.
- [ ] 11. Валидация OpenSpec вручную; `/project-checks` зелёный.
