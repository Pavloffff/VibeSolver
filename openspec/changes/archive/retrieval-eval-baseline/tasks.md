# Задачи: поиск по индексам и оценка качества

- [x] 1. Метрики: чистые функции `recall_at_k`, `mrr_at_k`, `ndcg_at_k` (файл-уровневая релевантность) + юнит-тесты на граничных случаях (пустая выдача, релевант вне топ-k, дубликаты файлов).
- [x] 2. Домен: сущности `SearchResult`, `SearchMeta`, ошибка `SearchUnavailableError`; протокол `RerankGateway`; тесты сущностей.
- [x] 3. `RetrievalUsecase`: выбор активных прогонов, эмбеддинг запроса, dense+lexical, RRF, top_k, сборка source_ref; юнит-тесты на фейковом `IndexSearchRepository` (в т.ч. 0 активных прогонов → SearchUnavailableError).
- [x] 4. `HttpRerankAdapter` (`{base}/rerank`, таймаут, понятные ошибки) + реестр адаптеров; юнит-тесты на парсинг ответа и отказ сервиса.
- [x] 5. Интеграция реранка в `RetrievalUsecase`: candidate_k = max(top_k×4, 32), деградация при отказе, `rerank_applied` в meta; тесты с фейковым шлюзом.
- [x] 6. API: `POST /api/v1/sources/{id}/search` (схемы SearchIn/SearchOut, 404/409/200), реэкспорт OpenAPI, тесты маршрута против dev-стека.
- [x] 7. Выделить общий гибридный поиск/RRF в `app/usecase/retrieval.py`; генерация материалов использует `rrf_fuse` вместо локальной копии (полное переключение на `RetrievalUsecase` — при добавлении агентного слоя).
- [x] 8. Golden set: формат + загрузчик YAML + валидация; стартовый `vibesolver.yaml` (15–20 запросов по этому репозиторию).
- [x] 9. Скрипт `scripts/eval_retrieval.py`: CLI (golden, top-k, пороги, out), отчёты JSON+Markdown, код возврата; интеграционный тест на dev-стеке.
- [x] 10. Доки: раздел «Поиск и оценка» в `docs/rag-and-indexing-guide.md` (эндпоинт, реранк-переменные, запуск оценки), упоминание в `docs/running.md`.
- [x] 10a. Dev-инструкция: как поднять TEI с bge-reranker локально (docker run) — в docs, без изменения compose по умолчанию.
