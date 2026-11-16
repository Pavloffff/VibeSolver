---
description: Draft an OpenSpec change (proposal + specs + design + tasks) before writing code
---

Draft a new OpenSpec change for: $ARGUMENTS

Follow `openspec/AGENTS.md` strictly:

1. Create `openspec/changes/<kebab-name>/` with `proposal.md` (why: current state → desired state), `specs/<capability>/spec.md` (delta headers `## ADDED/MODIFIED/REMOVED Requirements`, normative СИСТЕМА ДОЛЖНА wording, at least one `#### Сценарий:` with ДАНО/КОГДА/ТО), optional `design.md`, and numbered `tasks.md` (TDD order, tests first).
2. All artifacts in Russian; names kebab-case; statuses/data as registries, not closed DB enums.
3. End the reply with a short list of default decisions (veto points) and ask the user to validate. Do NOT start implementation before validation.
