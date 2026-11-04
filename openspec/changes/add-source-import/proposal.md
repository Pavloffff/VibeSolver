# Proposal: add-source-import

## Why

VibeSolver needs a knowledge layer before any agent can reason about a product. The first practical capability is importing source code: the user registers a code source (Git repository, local folder), the system fetches a snapshot, stores raw files in SeaweedFS (S3), and records metadata in PostgreSQL. This also establishes the repo layout, the infra, and both UI frontends (web + desktop) that all later capabilities build on.

## What Changes

### Capability: project-scaffold

Monorepo layout (per the official full-stack-fastapi-template convention): `backend/` (Python, uv, goose SQL migrations, FastAPI + Celery + Pydantic), `frontend/web/` (Vite + React + TS strict), `frontend/desktop/` (Electron wrapping the web UI), `build/` (run/build helpers, per-platform scripts), root `compose.yml` + `.env.example`, root build scripts `build-windows.ps1`, `build-linux.sh`, `build-mac.sh` + build instructions in README. CI basics: lint + pytest runnable locally.

### Capability: infra-local-remote

Two run modes for the desktop/web app:

- **Local mode**: docker-compose starts in background (postgres+pgvector, redis, seaweedfs master/volume/filer/s3 per the proven `D:\wb\data` pattern on `chrislusf/seaweedfs:4.17`, API, worker) — one click for a non-technical user.
- **Remote mode**: app connects to an existing server deployment by API base URL.

The app persists the chosen mode; switching is possible in settings.

### Capability: source-registry

REST API + web form to register/list/delete content sources. A source has: type (string key resolved against the connector registry — ships with git, local_folder, svn, hg; extensible), config (JSONB: url/path, branch, token ref), enabled flag. Registering a source enqueues a Celery import task. Import status is visible in UI (pending → running → done/failed).

The registry is self-describing: `GET /api/v1/connectors` returns registered connector types with `ready` flags and config schemas; the UI registration form is generated from this response (new connector → form appears without frontend changes).

### Capability: source-connector-spi

Python SPI that all source connectors implement: `validate_config(config) -> None (raises)`, `fetch_snapshot(config) -> Iterator[RawItem]` where `RawItem = {path, content_bytes, meta}`. Connectors are registered in a registry by type key. Adding a new VCS = new connector class + registry entry, no core changes (open-closed).

### Capability: git-connector

Fully working git connector: clone (with `--depth 1`), checkout branch, iterate files (respecting .gitignore, binary-file exclusion by extension list), stream each file as RawItem.

### Capability: local-folder-connector

Fully working local-folder connector: recursive walk, same exclusions as git connector.

### Capability: svn-mercurial-connector-skeletons

Registered svn and hg connectors that validate config and raise `NotImplementedError` on fetch — proving SPI extensensibility (for the thesis "connector SPI" argument).

### Capability: import-pipeline

Stage-based import pipeline ( extensibility-first): a Celery worker consumes an import task and runs a registry of stages over each source snapshot — **fetch** (connector) → **transforms** (empty in this change; future chunking/embedding/docstring stages plug in here without core changes) → **persist** (raw files to SeaweedFS bucket `raw` + `imported_files` rows in Postgres). Idempotent re-import (same source → re-fetch, upsert by source_id + path, keyed on content_hash — unchanged files are not re-uploaded). No chunking/embedding in this change — the pipeline shape is the point.

## Capabilities with no changes

- ticket pipeline (agents), retrieval, chunking, user flows — later changes.
- model training — non-goal entirely.

## Impact

- New code only; no existing code affected (greenfield).
- Security: tokens stored in DB referenced by name, never logged; `.env` never committed.