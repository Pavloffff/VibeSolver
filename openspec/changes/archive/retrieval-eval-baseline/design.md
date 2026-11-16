# Дизайн: поиск по индексам и оценка качества

## Архитектура

Слой за слоем по правилам DDD:

```
handler/routes/search.py      POST /api/v1/sources/{id}/search (тонкий роут)
usecase/retrieval.py          RetrievalUsecase: выбор прогонов, эмбеддинг запроса,
                              dense+lexical, RRF, опц. rerank, сборка результата
domain/repositories           IndexSearchRepository.search_dense/search_lexical (уже есть),
                              новый протокол RerankGateway
adapter/rerank.py             HttpRerankAdapter: POST {base}/rerank (OpenAI/Cohere/Jina/TEI-совместимый контракт)
```

`MaterialGenerationUsecase._retrieve_context` после этого переключается на `RetrievalUsecase` (удаляем дублирование RRF; квоты по типам индексов остаются в генерации — это политика генерации, не поиска).

## Детали поиска

- **Кандидаты**: для каждого выбранного `index_type` берём `project_indexes.active_run_id` (индекс со статусом `completed`); чанки только активных прогонов. Нет активных прогонов у всех выбранных типов → `SearchUnavailableError` → 409.
- **Гибридность**: запрос эмбеддится выбранной embedding-моделью проекта (роль `indexing`, существующий механизм `_embedding_target`); dense — косинус (`<=>`), lexical — `ts_rank` по `to_tsvector('simple')`. Слияние — RRF (k=60), формула уже реализована в `_rrf` и переезжает в usecase поиска.
- **top_k**: 1–50, по умолчанию 8. Для реранка набираем `candidate_k = max(top_k × 4, 32)` гибридных кандидатов.
- **source_ref**: `run:<run_id>:<path>:<start_line>` — совпадает с форматом, который генерация материалов уже кладёт в досье.

## Реранк

- Порт `RerankGateway.rerank(query, documents: list[str], top_n) -> list[(index, score)]` в domain.
- Адаптер `HttpRerankAdapter` — контракт `{base}/rerank`: `{"model": ..., "query": ..., "documents": [...], "top_n": n}` → `{"results": [{"index": i, "relevance_score": s}]}`. Это общий знаменатель Cohere/Jina/TEI/vLLM — локально поднимается TEI (text-embeddings-inference) с bge-reranker-v2-m3, облаком — Jina/Cohere.
- Конфиг окружением (скрытая возможность, без UI): `VIBESOLVER_RERANK_API_URL` (пусто = выключено), `VIBESOLVER_RERANK_MODEL`, `VIBESOLVER_RERANK_API_KEY` (опц.), `VIBESOLVER_RERANK_TIMEOUT_SECONDS`. Реестр адаптеров — словарь в adapter-слое, как у коннекторов и провайдеров.
- Отказ реранкера — деградация, не ошибка: результат гибридный, `meta.rerank_applied: false`, диагностика в ответ и лог. Ошибка 502 — только если реранкер вернул мусор и мы ПЫТАЛИСЬ его применить? Нет — всегда деградация: поиск не должен падать из-за вспомогательного этапа.
- Migration в реестр моделей (роль `rerank`, capability) — будущее изменение, когда появится UI-потребность.

## Золотой набор и метрики

- Формат `backend/eval/golden/<name>.yaml`:

```yaml
project: vibesolver          # имя проекта (source name) в dev-стеке
indexes: [code]              # какие индексы проверяем
queries:
  - query: "где обрабатывается распаковка архива"
    relevant: ["app/usecase/documentation_fs.py", "app/adapter/connectors/archive.py"]
    index_type: code
```

- Релевантность — по путям файлов (не по чанкам): recall@k = доля запросов, где в топ-k попал ХОТЯ БЫ один релевантный файл; для MRR — обратный ранг первого релевантного. nDCG@k — бинарная релевантность на уровне файла.
- Скрипт `backend/scripts/eval_retrieval.py` (CLI: `--golden <name> --top-k 10 --recall-at-10 <порог> --out <dir>`): ходит в API dev-стека (адрес из env), пишет `report.json` + `report.md` (таблица по типам индексов, проваленные запросы). Выход ≠ 0 при провале порога.
- Офлайн-метрики: чистые функции `recall_at_k/mrr_at_k/ndcg_at_k` в `app/usecase/retrieval_metrics.py` с юнит-тестами (формулы очевидны, RAGAS не тянем).
- Стартовый набор: `vibesolver.yaml` — 15–20 запросов по нашему же репозиторию (сам себе dogfooding: импортируем VibeSolver архивом и индексируем).

## Открытые вопросы (решения по умолчанию)

- Язык запросов в golden set — русский и английский вперемешку (реалии тикетов); tsvector-конфигурация `simple` не стеммит русский — известное ограничение, фиксить отдельно (настоящий BM25/стемминг — своё изменение).
- CORS/контракт: новый эндпоинт → обязательный реэкспорт OpenAPI и обновление теста контракта.
