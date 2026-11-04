# OpenSpec — Change Workflow

Conventions for creating and implementing changes under `openspec/changes/`.

## Creating a Change

When asked to propose a new capability or modification:

1. Create `openspec/changes/<change-name>/` with kebab-case name.
2. `proposal.md` — **Why** is this change being made? What problem does it solve? Current state → desired state.
3. `specs/<capability>/spec.md` — requirements with **delta** headers:
   - `## ADDED Requirements` / `## MODIFIED Requirements` / `## REMOVED Requirements`
   - Each requirement: `### Requirement: <name>` with **SHALL/MUST** wording + at least one `#### Scenario:` block ( GIVEN / WHEN / THEN ).
4. `design.md` (optional, for non-trivial changes) — technical context, decisions, trade-offs, alternative options considered.
5. `tasks.md` — numbered, checkable implementation checklist (checkboxes `- [ ]`), ordered by dependency; includes tests and docs steps.

Explore-mode research (`/opsx:explore`) goes into `proposal.md`/`design.md` — never directly into code.

## Validation (mandatory manual step)

Before `/opsx:apply`: re-read all artifacts, check for contradictions, duplicate requirements, loose ends, and unhandled edge cases. Ask the user clarifying questions. Iterate until the spec is consistent and complete.

## Implementation (`/opsx:apply`)

- Work through `tasks.md` in order, checking off items as they are completed.
- Tests first (TDD): each task that adds behavior gets a failing test before implementation.
- Keep implementation matching the spec — deviations require updating the spec first.

## Archiving (`/opsx:archive`)

When a change is fully implemented and validated: move the change folder to `openspec/changes/archive/<change-name>/`. Accumulated specs become the source of truth for the capability.

## Style

- Specs, proposals, designs: English, precise, SHALL/MUST normative wording.
- User-facing docs (README root, guides): Russian.
- Names: capabilities and changes in kebab-case (`ticket-triage`, `add-sandbox-executor`).