# Задачи: add-source-import

## 1. Каркас

- [x] 1.1 Создать структуру монорепо (конвенция full-stack-fastapi-template): `backend/app/{api,connectors,workers,storage,core}` + `backend/tests`, `frontend/web/` (заглушка Vite+React+TS), `frontend/desktop/` (заглушка), `build/`, `docs/`; обновить раздел о структуре репозитория в корневом `AGENTS.md`
- [x] 1.2 Проект backend: `pyproject.toml` (uv, зависимости: fastapi, uvicorn, celery, redis, sqlalchemy, psycopg, pydantic, boto3, dulwich; dev: pytest, ruff, mypy), зафиксированные версии
- [x] 1.3 Корневой `compose.yml`: postgres+pgvector (образ pgvector/pgvector), redis, seaweedfs master/volume/filer/s3 (chrislusf/seaweedfs:4.17, эталонный паттерн из D:\wb\data), api, worker; `.env.example` со всеми переменными
- [x] 1.4 Настройка goose: `backend/migrations/` + первая миграция `00001_sources.sql` (таблицы `sources`, `imports`, `imported_files`; БЕЗ CHECK-enum'ов — философия расширяемости: типы/статусы — данные реестра, а не схема); goose запускается из entrypoint контейнера api
- [x] 1.5 Корневые сборочные скрипты: `build-windows.ps1`, `build-linux.sh`, `build-mac.sh` (делегируют в `build/`), `build/start-local.*`, `build/build-desktop.*`; раздел README «Сборка» (необходимые компоненты + использование по ОС)

## 2. API реестра источников (сначала тесты)

- [x] 2.1 `тестер`: pytest-фикстуры — временный Postgres (docker) + httpx AsyncClient; тесты POST/GET/DELETE /api/v1/sources, включая сценарий ошибки валидации
- [x] 2.2 `кодер`: Pydantic-схемы + SQLAlchemy-модели + маршруты; хелпер, гарантирующий наличие бакета `raw` в `s3`
- [x] 2.3 `тестер`: тесты GET /api/v1/connectors (интроспекция реестра: типы, флаги ready, config_schema) + POST /api/v1/sources/{id}/import → 202 + endpoint статуса imports
- [x] 2.4 `кодер`: маршрут GET /api/v1/connectors (самоописание реестра); постановка импорта в очередь через Celery + маршрут последнего статуса `GET .../import`

## 3. Connector SPI + коннекторы (сначала тесты)

- [ ] 3.1 `тестер`: тесты SPI — реестр содержит git/local_folder/svn/hg, флаги `ready` корректны; svn/hg fetch кидает NotImplementedError
- [ ] 3.2 `кодер`: протокол `BaseConnector` + строго типизированный реестр (`dict[str, type[BaseConnector]]`) + config_schema на каждый коннектор (сериализованная Pydantic-схема) + скелеты svn/hg
- [ ] 3.3 `тестер`: тесты git-коннектора — клонирование маленького локального git-фикстурного репозитория, проверка отданных путей/исключений (.gitignore соблюдён, бинарные исключены, временная директория очищена)
- [ ] 3.4 `кодер`: git-коннектор (dulwich, --depth 1, checkout ветки, правила исключений)
- [ ] 3.5 `тестер`: тесты коннектора локальной папки — обход фикстурной папки, исключения
- [ ] 3.6 `кодер`: коннектор локальной папки (общий с git модуль исключений)

## 4. Конвейер импорта + стратегии хранения (сначала тесты)

- [ ] 4.1 `тестер`: тесты стадийного конвейера — контракт протокола PipelineStage, порядок STAGE_REGISTRY (fetch → persist), передача ctx; тесты стратегий: `git_reference` (загрузки контента нет, только манифест, строки с blob SHA) vs `full_copy` (контент загружен); идемпотентность: реимпорт того же контента → без повторной загрузки
- [ ] 4.2 `кодер`: стадийный воркер (протокол PipelineStage + реестр + ImportContext; стадия fetch; стадия persist с делегированием в реестр StorageStrategy: `git_reference`, `full_copy`; переопределение стратегии из конфига источника; обновления статуса imports, захват ошибок)
- [ ] 4.3 `тестер`: end-to-end — зарегистрировать локальный фикстурный источник через API → поставить в очередь → воркер (celery eager mode) → строки imported_files + файлы в S3; git-фикстурный источник со стратегией reference → манифест в S3, без копий контента

## 5. Веб-UI

- [x] 5.1 `кодер`: каркас `frontend/web/` (Vite + React + TS strict), типизированный API-клиент, список источников + форма регистрации, **генерируемая из GET /api/v1/connectors** (без хардкода списка типов) + кнопка импорта с опросом статуса
- [x] 5.2 Экран выбора режима (local/remote) + страница настроек; вызов проверки соединения
- [x] 5.3 `build/start-local`: корневой `docker compose up -d` из UI (локальный режим), детекция Docker с дружелюбной ошибкой
- [x] 5.4 i18n: словари `en`/`ru`/`zh` в `frontend/web/src/i18n/`, все строки через `t()`, переключение языка в настройках (по умолчанию `en`), с сохранением выбора

## 6. Десктоп

- [x] 6.1 `кодер`: `frontend/desktop/` — Electron-обёртка, загружающая сборку `frontend/web/`; сохранение конфигурации (режим, URL сервера)
- [x] 6.2 Конфиг electron-builder в `frontend/desktop/`; упаковка подключена к корневым `build-windows.ps1` / `build-linux.sh` / `build-mac.sh` (win exe, linux AppImage, mac dmg)

## 7. Ревью + интеграция

- [ ] 7.1 `ревьюер`: полное ревью по спеке (контракты, безопасность: токены не логируются, исключения корректны), проход по стилю
- [ ] 7.2 Исправить замечания, прогнать полный pytest + lint + mypy, ручной smoke: локальный режим поднят → импорт фикстурного репозитория → файлы в S3
- [ ] 7.3 Обновить разделы README по установке и сборке («Установка», «Сборка»: build-windows/linux/mac по ОС); архивировать изменение
