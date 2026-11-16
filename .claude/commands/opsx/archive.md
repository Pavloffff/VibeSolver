---
description: Archive a fully implemented and validated OpenSpec change
---

Archive the OpenSpec change: $ARGUMENTS

Preconditions (verify before moving anything):
- Every task in `tasks.md` is checked.
- `/project-checks` is green.
- The user has validated the delivery.

Steps: `git mv openspec/changes/<name> openspec/changes/archive/<name>`, then commit (message `chore: archive <name> openspec change`) after the user approves the commit.
