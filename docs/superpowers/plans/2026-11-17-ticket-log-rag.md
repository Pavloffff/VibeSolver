# Ticket Log RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Attach log archives to tickets, index them safely in an issue-isolated hybrid RAG corpus, and cite relevant log evidence in ticket analysis.

**Architecture:** Preserve raw archives in S3 and store attachment lifecycle in a ticket-owned table. A Celery task validates/extracts supported text, redacts sensitive values, chunks with file/line metadata, and writes ticket-scoped lexical/vector chunks. Retrieval uses the project's selected local embedding model and hybrid rank fusion, but requires both `source_id` and `ticket_id`; agent evidence includes only retrieved snippets.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL/pgvector, Celery, S3, existing embedding adapters, React/TypeScript, Vitest, pytest.

**Spec:** `openspec/changes/ticket-log-rag/specs/ticket-log-evidence/spec.md`; global design: `docs/superpowers/specs/2026-11-17-ticket-context-rag-design.md`.

## Global Constraints

- Scope every attachment and retrieval by both `source_id` and `ticket_id`.
- Do not include raw archives or entire project indexes in model prompts.
- Reject unsafe archive members and enforce compressed/unpacked size limits from settings.
- Keep processing local by default and redact secrets before embeddings and generation.
- Keep status and source registries extensible; do not add closed DB enums.
- Re-export both OpenAPI contracts after endpoint/schema changes.

## Review Focus

- Two tickets in one project: retrieval for one ticket cannot return the other's chunks.
- Traversal paths, symlinks, malformed archives, and decompression bombs: reject safely without ready status.
- Binary and invalid UTF-8 files: never embed; report diagnostics.
- Ticket run while attachment is queued/processing/failed: return a readable conflict.
- Upload succeeds in S3 but DB/queue fails: no falsely ready attachment or leaked orphan object.

---

### Task 1: Safe log extraction and chunking

**Files:**
- Create: `backend/app/usecase/ticket_logs.py`
- Create: `backend/tests/test_ticket_logs.py`
- Reuse: `backend/app/usecase/documentation_fs.py`

- [x] Test supported archive extraction, supported text suffixes, UTF-8/BOM, UTF-16/BOM, Windows-1251/1252, binary skips, unsafe paths, unpacked limit, and line-preserving chunks.
- [x] Run targeted pytest and confirm failures because the log parser is missing.
- [x] Implement typed extraction results and deterministic chunks with relative paths and line ranges; use existing safe archive reader.
- [x] Run targeted pytest and confirm all cases pass.

### Task 2: Attachment persistence and processing lifecycle

**Files:**
- Create migration in `backend/migrations/`
- Modify `backend/app/domain/tickets.py`, `backend/app/domain/repositories/tickets.py`, `backend/app/adapter/repositories/tickets.py`
- Modify `backend/app/handler/routes/tickets.py`, `backend/app/handler/schemas.py`
- Modify `backend/app/adapter/celery_app.py` and add a ticket log worker module
- Tests in `backend/tests/`

- [ ] Add failing repository/API tests for upload/list/status/retry/delete, ticket ownership, archive validation, S3 lifecycle, and queue failure.
- [ ] Add migration and typed repository/usecase lifecycle, raw S3 artifact metadata, and Celery processing statuses; export OpenAPI after API changes.
- [ ] Run focused tests and OpenAPI contract checks.

### Task 3: Ticket-scoped hybrid index and agent evidence

**Files:**
- Add ticket-log chunk/search repositories and migration-backed models.
- Modify `backend/app/usecase/retrieval.py`, `backend/app/usecase/ticket_agent.py`, related dependency wiring.
- Add tests for dense/lexical fusion, mandatory ticket scope, citation provenance, run readiness gate, OOM/disk-full evidence.

- [ ] Write failing retrieval and agent tests before implementation.
- [ ] Reuse embedding provider selection, optional rerank, RRF fusion, candidate limits, and existing per-ticket context budget.
- [ ] Ensure project-wide retrieval cannot enumerate or search ticket-log indexes.
- [ ] Run focused and full backend checks.

### Task 4: Ticket UI and final verification

**Files:**
- Modify `frontend/web/src/pages/issues-page/ui/IssuesPage.tsx`, API types/client, translations, CSS, tests.

- [ ] Write failing UI tests for attach/list/status/retry/remove and disabled run until ready.
- [ ] Implement accessible archive controls and localized error/status messages in en/ru/zh.
- [ ] Run frontend tests, lint, build, OpenAPI validation, backend lint/typecheck/tests, and `git diff --check`.
- [ ] Manually validate proposal/spec/tasks against implementation; note unavailable infrastructure in results.
