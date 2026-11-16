---
description: Implement an OpenSpec change task by task with tests first, checking off tasks.md
---

Implement the OpenSpec change: $ARGUMENTS

Rules from `openspec/AGENTS.md` and `AGENTS.md`:

1. Work through `tasks.md` in order, checking off `- [x]` items as they complete.
2. Tests first: every task that adds behavior gets a failing test before implementation.
3. Implementation must match the spec; deviations require updating the spec first.
4. After ANY endpoint/schema change re-export OpenAPI (`uv run python scripts/export_openapi.py` in `backend`) and commit both files with the code.
5. Run `/project-checks` before finishing; report deviations from tasks.md.
6. Do not commit without the user's explicit approval.
