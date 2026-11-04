# AGENTS.md — VibeSolver

Guidelines for AI coding agents working in this repository.

## Project Overview

VibeSolver is a multi-agent system for triaging and resolving IT support tickets, powered by RAG over the product's source code, technical documentation, user flows, and ticket history. Two layers:

- **Knowledge layer** — ingestion pipeline: Git/Confluence import → AST-aware chunking (tree-sitter) → embeddings (bge-m3) → hybrid search (pgvector + BM25 + rerank).
- **Ticket layer** — LangGraph agent pipeline: Triage → Log/Screen Analyzer → Code Investigator → Fix Writer (sandboxed) → Human Approval → MR Builder / Escalation.

Detailed project context: `openspec/project.md`. Workflow conventions: `openspec/AGENTS.md`.

## Project Philosophy

Two pillars for every decision:

1. **User convenience** — the product must be easy for a non-technical user: one-click local mode, clear errors, web and desktop parity.
2. **Extensibility** — never hardcode closed sets of options (connector types, source kinds, chunk kinds, routes). Use registries/SPIs open for extension without core changes (open-closed). No CHECK-constraint-style enums in the DB where growth is expected — enums as data (registry/config), not as schema. Hidden-but-working features are OK: e.g. git multi-branch import works in the backend (config key `branches`), but the field is NOT exposed in connector `config_fields` until the product is ready (user decision — import defaults to the default branch).
3. **User-first UI wording** — product terms are user-facing: "Projects" (not "Sources"), "Remote server" (not "On server"), "Local" implies the bundled API URL with zero configuration. Fields self-explain: password fields carry a `hint` with instructions (e.g. how to obtain a PAT), path fields offer a folder picker (native dialog in desktop, webkitdirectory fallback in browser). Backend validation errors must be human-readable ("unknown repo (clone failed): <url>"), never raw tracebacks.

## Hard Rules

- **OpenAPI contract lives in `backend/api/`.** `openapi.json` + `openapi.yaml` are exported from the FastAPI app (`uv run python scripts/export_openapi.py`) — code is the source of truth. After ANY endpoint/schema change: re-export and commit both files together with the code. CI/tests (`backend/tests/test_openapi_contract.py`) validate the files against the OpenAPI 3.1 spec and fail on drift between contract and app.
- **Compose file is named `docker-compose.yml`** (never `compose.yml`), at repo root.
- **Language split: agent-facing = English, human-facing = Russian.** Agent-read files (this AGENTS.md, `openspec/AGENTS.md`, prompts) — English. Human-read files (all spec artifacts `openspec/**` incl. proposals/specs/design/tasks, `docs/**`, user-facing README) — Russian. Code, identifiers, commit messages, `.env` — English. When in doubt: if the user reviews/approves it — Russian; if an agent consumes it as instructions — English.
- **No secrets or environment-specific config in constants.** All URLs, hosts, ports, credentials, tokens, and tunables come from environment variables via `.env` (backend: pydantic-settings reading env prefix; frontend: runtime config, never baked into the bundle). `.env` is never committed; `.env.example` documents every variable with safe defaults. If a value could differ between dev/prod/machine — it belongs in env, not in code.
- **i18n from day one.** All user-facing strings go through a translation dictionary (no inline literals in components). Supported languages: English (default), Russian, Chinese. Language is a user setting in the UI. Adding a language = adding a dictionary file, no code changes.

## Architecture Conventions (DDD)

Backend follows **DDD layering** (modular monolith — see `docs/adr/0001-modular-monolith.md`):

```
backend/app/
├── domain/     # entities (SQLAlchemy models), repository INTERFACES (protocols), value objects — no infra deps
├── usecase/    # business logic: register source, run import pipeline (stage orchestration) — depends on domain only
├── adapter/    # infra implementations: db (SQLAlchemy repos), s3, source connectors, celery, config (pydantic-settings)
└── handler/    # FastAPI routers/schemas — thin HTTP layer, delegates to usecase
```

- Dependency direction: `handler → usecase → domain`; `adapter` implements domain interfaces and is injected into usecase. Domain never imports adapter/handler.
- Frontend follows **Feature-Sliced Design (FSD)**: layers `app → pages → widgets → features → entities → shared`; each layer may only import from layers below; API clients and i18n in `shared`, source-related UI in `entities`/`features`.

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React, TypeScript |
| API | Python 3.12+, FastAPI, Celery, Redis |
| Agent engine | LangGraph, Pydantic (strict structured outputs) |
| Storage | PostgreSQL + pgvector (chunks, tickets, flows), SeaweedFS (S3, artifacts) |
| Chunking | tree-sitter (code, AST-based), unstructured (docs) |
| Retrieval | bge-m3 embeddings, bge-reranker, RRF fusion, hybrid dense+BM25 |
| Eval | RAGAS, golden-set of historical tickets |
| Sandbox | Docker `--network none`, CPU/RAM limits |
| LLM | via unified LLM gateway: cloud (DeepSeek, Z.ai GLM), local (Qwen, gpt-oss) — model per agent is config |
| Observability | Langfuse |
| Deploy | docker-compose, single host |

## Commands

```bash
# Backend
uv sync                        # install deps (uv as package manager)
uv run pytest                   # tests
uv run ruff check .             # lint
uv run ruff format .            # format
uv run mypy app                 # typecheck

# Frontend (frontend/web/)
npm ci
npm run build
npm run lint
npm test

# Infra
docker compose up -d            # postgres+pgvector, redis, seaweedfs, langfuse
docker compose up api worker    # app services

# Migrations (goose; also run by the api container entrypoint)
goose -dir backend/migrations postgres "$VIBESOLVER_DATABASE_URL" up
```

When adding a new source connector, a new agent, or a new metric — write tests first (TDD). Tests must fail before implementation exists.

## Code Style

### Python
- Type hints everywhere; `mypy` in strict mode must pass.
- Pydantic models for all data crossing agent/service boundaries. No free-form dicts between agents.
- No comments unless explicitly requested. Self-documenting names.
- Errors: raise specific exceptions; never swallow silently.
- Async-first in API and workers; sync code only in pure computation helpers.
- Dependencies must be pinned (no `latest`); new deps → run a vulnerability check (`pip-audit`) and note license.

### TypeScript / React
- Strict `tsconfig`; no `any` unless unavoidable (then `unknown`).
- Functional components, hooks; no class components.
- API types generated/validated against backend Pydantic schemas (single source of truth).

### Agents (LangGraph)
- One agent = one narrow responsibility, one prompt, one Pydantic output contract.
- Graph edges are deterministic routing decisions (`route: auto_fix | escalate | answer`).
- Iteration limits are mandatory for any loop (e.g., Fix Writer ↔ Investigator, max 3).
- Every agent step writes to `trace` (append-only) — needed for eval and escalation dossiers.
- Sandbox: agents never execute generated code directly; only the Sandbox Executor runs it (`docker --network none`).

### Data / privacy
- Personal data and product code stay local (local LLMs). Cloud LLMs receive only de-identified text — see data-flow rules in spec `data-handling`.
- Never log secrets, tokens, or raw user PII. Env vars via `.env` (never committed).

## Git Conventions

- Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- Small, focused commits. One logical change per commit.
- Never force-push, never amend published commits, never commit secrets.
- NEVER commit or push without the user's review first. Workflow: finish work → report what changed → user reviews and says "commit" → only then commit+push. A commit/push instruction authorizes that specific changeset only.

## Workflow (Spec-Driven Development)

This repo follows OpenSpec conventions (see `openspec/AGENTS.md`):

1. `/opsx:propose` — draft `proposal.md` + `specs/` + `tasks.md` under `openspec/changes/<name>/` before writing code for any non-trivial feature.
2. `/opsx:explore` — research questions and alternatives; findings go into the change, not the code.
3. **Validate** specs for contradictions and loose ends (manual step — mandatory).
4. `/opsx:apply` — implement task by task, checking off `tasks.md`.
5. `/opsx:archive` — move completed change to archive.

Rules of thumb:
- Specs are written by the smartest available model; implementation may use a cheaper one; review uses a smart model again.
- A spec is done when further refinement causes fatigue — not before.
- ALL spec artifacts (proposal.md, specs/, design.md, tasks.md) and docs are in **Russian**. Code, identifiers, commit messages in English.

## Repo Layout

```
openspec/          # spec-driven development: project.md, changes/, specs archive
backend/
  app/
    api/           # FastAPI app factory, routes
    connectors/    # source connectors, CONNECTOR_REGISTRY
    workers/       # Celery app, import tasks
    storage/       # SeaweedFS (S3) client helpers
    core/          # settings
  migrations/      # goose SQL migrations
  tests/           # backend tests
frontend/
  web/             # Vite + React + TS frontend
  desktop/         # Electron wrapper around frontend/web
build/             # per-platform build/start helpers
infra/             # docker-compose assets (seaweedfs s3 config)
docs/              # architecture decisions (C4), diagrams
```