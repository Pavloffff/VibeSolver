# Ticket LangGraph Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current ticket orchestration with a LangGraph StateGraph while preserving runtime behavior and trace.

**Architecture:** Compile a typed, conditional StateGraph in `TicketAgentUsecase`, using existing methods as work units and append-only `ticket_steps` as the durable trace. Keep HTTP/API behavior and preflight outside the graph; do not add checkpointing, code execution, sandboxing, or test-running nodes.

**Tech Stack:** Python 3.12, LangGraph, Pydantic, pytest.

**Spec:** `openspec/changes/ticket-langgraph-orchestration/`

## Global Constraints

- Backend dependencies are exactly pinned in `backend/pyproject.toml` and `backend/uv.lock`.
- Agent outputs crossing model boundaries remain strict Pydantic schemas.
- No generated code executes in the ticket graph.
- Preserve append-only trace records and current routing outcomes.

## Review Focus

- Empty dossier skips resolver and stores the existing escalation trace.
- Invalid citations never produce an answered ticket.
- Model selection failures restore the previous ticket status.
- Unexpected node errors mark the ticket failed.
- Current operation has no cycles and has a finite recursion limit.

---

### Task 1: Typed LangGraph topology and dependency

**Files:** `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/usecase/ticket_agent.py`, `backend/tests/test_ticket_agent.py`.

- [x] Pin LangGraph; update lock.
- [x] Write topology test: compiled graph contains ordered nodes and conditional branches for empty dossier, answer, and escalation.
- [x] Run test and confirm it fails because the compiled graph is not present.
- [x] Implement `TicketGraphState`, graph builder, and named nodes using existing use case operations.
- [x] Run focused test and confirm it passes.

### Task 2: Route `run` through graph and preserve outcomes

**Files:** `backend/app/usecase/ticket_agent.py`, `backend/tests/test_ticket_agent.py`.

- [x] Add a regression assertion that one successful graph run preserves trace order and ticket response.
- [x] Route `run` through async graph invocation with explicit recursion limit.
- [x] Verify empty dossier, resolver escalation, invalid refs, missing model, log readiness conflict, and provider failure cases.

### Task 3: Verify and document

**Files:** `docs/ticket-agent.md`, OpenSpec task list.

- [x] Update docs to describe LangGraph topology and explicitly state sandbox/test execution is out of scope.
- [x] Run backend tests, `ruff`, and `mypy`; confirm OpenAPI is unchanged.
- [x] Mark implementation tasks complete after manual spec review.
