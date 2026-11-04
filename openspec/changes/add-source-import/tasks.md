# Tasks: add-source-import

## 1. Scaffold

- [x] 1.1 Create monorepo layout (full-stack-fastapi-template convention): `backend/app/{api,connectors,workers,storage,core}` + `backend/tests`, `frontend/web/` (Vite+React+TS placeholder), `frontend/desktop/` (placeholder), `build/`, `docs/`; update root `AGENTS.md` repo layout to match
- [x] 1.2 Backend project: `pyproject.toml` (uv, deps: fastapi, uvicorn, celery, redis, sqlalchemy, psycopg, pydantic, boto3, dulwich; dev: pytest, ruff, mypy), pinned versions
- [x] 1.3 Root `compose.yml`: postgres+pgvector (pgvector/pgvector image), redis, seaweedfs master/volume/filer/s3 (chrislusf/seaweedfs:4.17, reference pattern from D:\wb\data), api, worker; `.env.example` with all vars
- [x] 1.4 Goose setup: `backend/migrations/` + first migration `00001_sources.sql` (`sources`, `imports`, `imported_files` tables; NO CHECK enums — extensibility philosophy: types/statuses are registry-driven data, not schema); goose runs from api container entrypoint
- [x] 1.5 Root build scripts: `build-windows.ps1`, `build-linux.sh`, `build-mac.sh` (delegate to `build/`), `build/start-local.*`, `build/build-desktop.*`; README section «Сборка» (prerequisites + usage per OS)

## 2. Source registry API (tests first)

- [ ] 2.1 `тестер`: pytest fixtures — temp Postgres (docker) + httpx AsyncClient; tests for POST/GET/DELETE /api/v1/sources incl. validation-error scenario
- [ ] 2.2 `кодер`: Pydantic schemas + SQLAlchemy models + routes; `s3` bucket `raw` ensure helper
- [ ] 2.3 `тестер`: tests for GET /api/v1/connectors (registry introspection: types, ready flags, config_schema) + POST /api/v1/sources/{id}/import → 202 + imports status endpoint
- [ ] 2.4 `кодер`: GET /api/v1/connectors route (registry self-description); import enqueue via Celery + `GET .../import` latest-status route

## 3. Connector SPI + connectors (tests first)

- [ ] 3.1 `тестер`: SPI tests — registry lists git/local_folder/svn/hg, `ready` flags correct; svn/hg fetch raises NotImplementedError
- [ ] 3.2 `кодер`: `BaseConnector` protocol + strongly-typed registry (`dict[str, type[BaseConnector]]`) + config_schema per connector (Pydantic schema serialized) + svn/hg skeletons
- [ ] 3.3 `тестер`: git connector tests — clone a small local git fixture repo, assert yielded paths/exclusions (.gitignore respected, binary excluded, temp dir cleaned)
- [ ] 3.4 `кодер`: git connector (dulwich, --depth 1, branch checkout, exclusion rules)
- [ ] 3.5 `тестер`: local-folder connector tests — walk fixture folder, exclusions
- [ ] 3.6 `кодер`: local-folder connector (shared exclusion module with git)

## 4. Import pipeline (tests first)

- [ ] 4.1 `тестер`: stage-pipeline tests — PipelineStage protocol contract, STAGE_REGISTRY ordering (fetch → persist), ctx passing; worker tests — RawItem → fake S3 (moto) upload + `imported_files` upsert; idempotency: re-import same content → no re-upload
- [ ] 4.2 `кодер`: stage-based worker (PipelineStage protocol + registry + ImportContext; fetch stage, persist stage; uploads, upserts, imports status updates, error capture)
- [ ] 4.3 `тестер`: end-to-end — register local fixture source via API → enqueue → worker (celery eager mode) → imported_files rows + files in S3

## 5. Web UI

- [x] 5.1 `кодер`: `frontend/web/` scaffold (Vite + React + TS strict), typed API client, source list + register form **generated from GET /api/v1/connectors** (no hardcoded type list) + import button with status polling
- [x] 5.2 Mode selection screen (local/remote) + settings page; connection check call
- [x] 5.3 `build/start-local`: root `docker compose up -d` from UI (local mode), Docker detection with friendly error
- [x] 5.4 i18n: dictionaries `en`/`ru`/`zh` in `frontend/web/src/i18n/`, all strings through `t()`, language switch in Settings (default `en`), persisted

## 6. Desktop

- [x] 6.1 `кодер`: `frontend/desktop/` Electron wrapper loading the `frontend/web/` build; config persistence (mode, server URL)
- [x] 6.2 electron-builder config in `frontend/desktop/`; packaging wired to root `build-windows.ps1` / `build-linux.sh` / `build-mac.sh` (win exe, linux AppImage, mac dmg)

## 7. Review + integration

- [ ] 7.1 `ревьюер`: full review vs spec (contracts, security: tokens not logged, exclusions correct), style pass
- [ ] 7.2 Fix findings, run full pytest + lint + mypy, manual smoke: local mode up → import fixture repo → files in S3
- [ ] 7.3 Update README install + build sections («Установка», «Сборка»: build-windows/linux/mac per OS); archive change