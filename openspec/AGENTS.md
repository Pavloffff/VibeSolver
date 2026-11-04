# OpenSpec — Change Workflow

Conventions for creating and implementing changes under `openspec/changes/`.

## Creating a Change

When asked to propose a new capability or modification:

1. Create `openspec/changes/<change-name>/` with a kebab-case name.
2. `proposal.md` — **why** is this change being made? What problem does it solve? Current state → desired state.
3. `specs/<capability>/spec.md` — requirements with **delta** headers:
   - `## ADDED Requirements` / `## MODIFIED Requirements` / `## REMOVED Requirements`
   - Each requirement: `### Requirement: <name>` with normative **SHALL/MUST** wording and at least one `#### Scenario:` block (GIVEN / WHEN / THEN).
4. `design.md` (optional, for non-trivial changes) — technical context, decisions, trade-offs, alternatives considered.
5. `tasks.md` — numbered, checkable implementation checklist (`- [ ]`), ordered by dependency; includes tests and docs steps.

Explore-mode research (`/opsx:explore`) findings go into `proposal.md`/`design.md` — never directly into code.

## Validation (mandatory manual step)

Before `/opsx:apply`: re-read all artifacts, check for contradictions, duplicate requirements, loose ends, unhandled edge cases. Ask the user clarifying questions. Iterate until the spec is consistent and complete.

## Implementation (`/opsx:apply`)

- Work through `tasks.md` in order, checking off completed items.
- Tests first (TDD): every task that adds behavior gets a failing test before implementation.
- Implementation must match the spec — deviations require updating the spec first.

## Archiving (`/opsx:archive`)

When a change is fully implemented and validated: move the change folder to `openspec/changes/archive/<change-name>/`. Accumulated specs become the source of truth for the capability.

## Style (language split)

- Spec artifacts (proposals, specs, designs, tasks) — **Russian** (the user reviews and approves them; normative СИСТЕМА ДОЛЖНА/ОБЯЗАНА wording, ДАНО/КОГДА/ТО scenarios).
- Code, identifiers, commit messages — English.
- User-facing documentation (root README, guides in `docs/`) — Russian.
- Agent-facing instruction files (AGENTS.md, this file) — English.
- Names: capabilities and changes — kebab-case (`ticket-triage`, `add-sandbox-executor`).