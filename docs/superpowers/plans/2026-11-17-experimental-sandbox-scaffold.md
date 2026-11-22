# Experimental Sandbox Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish an experimental, default-off sandbox execution contract and testable Docker plan without running commands.

**Architecture:** Define request/result types and a protocol in the domain layer. Add an adapter that validates an immutable resource policy and constructs an argv plan only; do not connect Docker, subprocess, HTTP, UI, or LangGraph.

**Tech Stack:** Python 3.12, Pydantic or dataclasses, pytest, pydantic-settings.

**Spec:** `openspec/changes/experimental-sandbox-scaffold/`

## Global Constraints

- `VIBESOLVER_EXPERIMENTAL_SANDBOX_ENABLED` defaults to false.
- The plan requires no network, readonly inputs, isolated tmpfs workspace, dropped capabilities, no-new-privileges, CPU/RAM/PID/time limits, and a digest-pinned image.
- No command execution or Docker daemon access is introduced.

## Review Focus

- Missing enable flag never generates an executable plan.
- Tag-based image references are rejected; digest-pinned references are accepted.
- Workspace paths containing spaces remain a single argv value.
- Nonpositive or excessive resource limits fail validation.
- The graph remains disconnected from the sandbox protocol.

---

### Task 1: Domain contract

- [x] Test request/response model validation and protocol shape.
- [x] Run tests and verify the missing contract fails.
- [x] Add typed domain contract.

### Task 2: Safe plan builder

- [x] Test disabled default, digest validation, safe argv and rejection of invalid limits.
- [x] Add default-off env settings and pure Docker argv builder; no subprocess execution.
- [x] Run tests and verify command plan generation.

### Task 3: Integration boundary and verification

- [x] Add env wiring and docs; graph remains disconnected.
- [x] Run full backend suite, `ruff`, `mypy`, and `pip-audit`.
- [x] Manually verify OpenSpec scope and mark tasks complete.
