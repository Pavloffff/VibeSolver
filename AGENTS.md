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
2. **Extensibility** — never hardcode closed sets of options (connector types, source kinds, chunk kinds, routes). Use registries/SPIs open for extension without core changes (open-closed). No CHECK-constraint-style enums in the DB where growth is expected — enums as data (registry/config), not as schema.

## Hard Rules

- **No secrets or environment-specific config in constants.** All URLs, hosts, ports, credentials, tokens, and tunables come from environment variables via `.env` (backend: pydantic-settings reading env prefix; frontend: runtime config, never baked into the bundle). `.env` is never committed; `.env.example` documents every variable with safe defaults. If a value could differ between dev/prod/machine — it belongs in env, not in code.
- **i18n from day one.** All user-facing strings go through a translation dictionary (no inline literals in components). Supported languages: English (default), Russian, Chinese. Language is a user setting in the UI. Adding a language = adding a dictionary file, no code changes.

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
- Write specs/README/docs prose in Russian where user-facing (README, doc sites); keep code, identifiers, commit messages, and internal docs in English.

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