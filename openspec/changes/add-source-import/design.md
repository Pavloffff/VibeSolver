# Design: add-source-import

## Context

Greenfield first change: repo layout + infra + source import. Knowledge layer starts with raw file storage; chunking/embedding is out of scope (next change).

## Decisions

- **Monorepo** (per the official full-stack-fastapi-template layout, the community-proven convention): `backend/` (single Python package `app`), `frontend/web/` (Vite + React + TS strict), `frontend/desktop/` (Electron wrapper of the same web build), `build/` (shared build helpers), root `compose.yml` + `.env.example`, root per-platform build scripts `build-windows.ps1` / `build-linux.sh` / `build-mac.sh` (each delegates to `build/`), build instructions in README. npm projects stay plain (no nx/turbo); shared UI code via a local package if duplication appears.
- **Electron** (user decision over Tauri/RN): `frontend/desktop` loads the built `frontend/web` bundle; one React+TS codebase. Packaging via `electron-builder` for win/linux/mac driven by the root build scripts.
- **Connector SPI** in `backend/app/connectors/`: registry dict + `BaseConnector` protocol. Git via `dulwich` (pure-python, no git binary dependency) — fallback consideration: subprocess git if dulwich is too slow on big repos.
- **SeaweedFS**: same topology as the proven reference deployment (`chrislusf/seaweedfs:4.17`: master → volume → filer → s3 gateway, port 8333, s3.json config). S3 client: `boto3` pointed at the gateway.
- **Import pipeline is stage-based from day one** (user decision): `PipelineStage` protocol + `STAGE_REGISTRY` (ordered list: fetch → persist; transforms empty now). Future chunking/embedding/docstring/flow stages register into the same pipeline — no worker rework. Stage contract: `run(snapshot: Iterator[RawItem], ctx: ImportContext) -> ...` with ctx carrying source config, db session, s3 client.
- **Import status without polling complexity**: import task writes status rows to Postgres (`imports` table: status values, progress counter, error text — plain TEXT, no DB enums); API exposes latest row. Celery result backend not used for status (restart-safe).
- **Registry is self-describing**: `GET /api/v1/connectors` exposes the connector registry (type key, ready flag, config schema) so the UI form is generated from data — frontend never hardcodes the type list (extensibility philosophy).
- **DB**: migrations via **goose** (plain SQL migrations in `backend/migrations/`, no Alembic — user decision). Tables: `sources`, `imports`, `imported_files`.
- **Local mode**: `build/start-local` runs `docker compose up -d` (root `compose.yml`) from the desktop app shell (with Docker detection + clear error if missing). Remote mode: just base URL.
- **Build scripts**: root `build-windows.ps1` / `build-linux.sh` / `build-mac.sh` — full packaging pipelines (backend docker image + frontend build + electron-builder for the host OS), sharing logic via `build/`; README "Сборка" section documents prerequisites and usage per OS.
- **Scope guard**: this change imports CODE ONLY (git, local_folder + svn/hg skeletons). No docs/wiki/Confluence, no user flows, no chunking, no embeddings — explicitly deferred to later changes.

## Risks / Trade-offs

- dulwich clone of huge repos may be slow — acceptable for MVP; measured on the golden repo.
- Electron binary ~100MB — accepted by user (chose Electron over Tauri).
- No chunking yet: files stored raw; retrieval change will consume `imported_files`.