---
description: Run the full check suite (backend + frontend + OpenAPI contract)
---

Run all project checks and report a compact pass/fail summary.

Backend (from `backend/`; use `uv run --no-sync` when the venv is already synced):

```
uv run pytest
uv run ruff check .
uv run mypy app
uv run python scripts/export_openapi.py && git diff --exit-code api/ || echo "OpenAPI drift: re-export and include in the commit"
```

Frontend (from `frontend/web/`):

```
npm run lint
npm test
npm run build
```

DB-backed tests need the dev stack (`docker compose up -d postgres seaweed-s3`) and goose migrations applied; report them as skipped rather than starting heavy infra unless the user asks. If a failure is environmental (CPU-load flakiness, unreachable network), rerun once, then report it as such instead of chasing it.
