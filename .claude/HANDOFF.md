# HANDOFF — cost-routing: реализация завершена, финальная проверка ограничена средой (17.11.2026)

## Текущее состояние

Фаза 3 реализована в рабочем дереве поверх WIP-коммита `f22ee68`. Задачи 1–10 в `openspec/changes/cost-routing/tasks.md` отмечены выполненными. Изменения не закоммичены. Файл удалить после завершения пункта 11 и архивации change.

Реализация включает usage и цены LLM-шагов, каскад моделей triage/strong/cheap, статистику обращений (`GET /api/v1/sources/{id}/tickets/stats`), три селектора ролей и карточку метрик в UI. OpenAPI экспортирован в `backend/api/openapi.json` и `backend/api/openapi.yaml`; документация обновлена в `docs/ticket-agent.md` и `docs/running.md`.

## Осталось

1. Повторить полный `/project-checks` в окружении с доступным PostgreSQL и корректной POSIX-папкой `/tmp`; затем вручную закрыть пункт 11.
2. После успешной проверки заархивировать `openspec/changes/cost-routing/` и удалить этот handoff.
3. Не коммитить и не пушить до ревью пользователя.

## Последние проверки

- Backend: `ruff check .` и `mypy app` прошли.
- Целевые backend-тесты: 38 passed, 3 skipped; тесты OpenAPI-контракта прошли.
- Frontend: lint прошёл, 26 тестов прошли, production build прошёл.
- Полный backend pytest с `--basetemp` внутри разрешённой рабочей области: 156 passed, 34 skipped, 2 failed. Оба отказа — `tests/test_retrieval_eval.py` записывает `Path("/tmp/sample.yaml")`, что недоступно в Windows sandbox. DB-тесты пропущены: PostgreSQL не доступен. Согласно `.claude/commands/project-checks.md`, не запускать тяжёлую инфраструктуру и не обходить эти ограничения; зафиксировать их в отчёте.

## Контекст реализации

- Полный перечень изменений и команды проверок — в `openspec/changes/cost-routing/tasks.md` и `.claude/commands/project-checks.md`.
- Текущий рабочий diff принадлежит этой фазе; перед коммитом просмотреть его целиком.
