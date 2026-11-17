# Задачи: ticket-scoped RAG для логов

- [ ] 1. Спроектировать миграции артефактов логов и ticket-scoped chunks/index state; тестами зафиксировать isolation по `(source_id, ticket_id)` и жизненный цикл версий.
- [x] 2. Добавить безопасный parser/chunker архивов: `.zip`/`.tar.gz`, текстовые форматы, UTF-8/BOM, UTF-16/BOM, Windows-1251/1252, пути, лимиты распаковки, строки/временные метки, секреты и диагностика; написать тесты на traversal, zip bomb, binary и malformed entries.
- [ ] 3. Добавить API upload/list/status/retry/delete для attachment, хранение исходного архива в S3 и Celery-задачу обработки с понятными статусами; обновить OpenAPI.
- [ ] 4. Реализовать создание embeddings и гибридный dense+BM25 retrieval с обязательным ticket scope; покрыть unit и repository/API tests.
- [ ] 5. Подключить ticket-log retrieval к dossier ticket-agent, citation references и запуск только при готовых вложениях; покрыть тестами run gate, retrieval isolation, ссылки и эксплуатационные причины.
- [ ] 6. Добавить UI прикрепления архива, список вложений/статусов, retry и блокировку запуска до готовности; добавить локализацию en/ru/zh и frontend tests.
- [ ] 7. Обновить документацию, экспортировать OpenAPI, вручную валидировать change и запустить допустимые backend/frontend проверки; зафиксировать ограничения окружения.
