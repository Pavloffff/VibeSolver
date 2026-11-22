# Ticket Text Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a user prefill the existing issue form from a `.txt` file and edit the parsed values before submission.

**Architecture:** Parse text in a pure feature helper; keep issue creation on the existing form and API path. The page handles file selection, localized errors, and form state.

**Tech Stack:** React, TypeScript, Vitest, Testing Library, existing i18n dictionaries.

**Spec:** `openspec/changes/ticket-text-import/specs/ticket-intake/spec.md`; broader roadmap: `docs/superpowers/specs/2026-11-17-ticket-context-rag-design.md`.

## Global Constraints

- User-facing strings MUST use English, Russian, and Chinese translation dictionaries.
- Keep the imported title and description editable; importing a file MUST NOT submit the form.
- Preserve the current ticket API contract.

## Review Focus

- Empty or whitespace-only file: show an error and do not change values or submit.
- File with title but no useful description: show a localized validation error and do not submit.
- CRLF and leading blank lines: parse title and description consistently.
- Non-TXT file: reject before reading and leave current form values unchanged.
- File-reader failure: show a localized error and allow retry.

---

### Task 1: Pure TXT parser

**Files:**
- Create: `frontend/web/src/features/issues/lib/parseTicketText.ts`
- Create: `frontend/web/src/features/issues/lib/parseTicketText.test.ts`

- [x] Write tests for first nonempty line, CRLF, leading blank lines, empty input, and missing description.
- [x] Run the targeted Vitest test and confirm it fails because the parser is missing.
- [x] Implement `parseTicketText(text: string): { title: string; description: string } | null`; trim title and description, ignore leading blank lines, and preserve internal description newlines.
- [x] Run the targeted Vitest test and confirm it passes.

### Task 2: Form import and localized feedback

**Files:**
- Modify: `frontend/web/src/pages/issues-page/ui/IssuesPage.tsx`
- Modify: `frontend/web/src/__tests__/IssuesPage.test.tsx`
- Modify: `frontend/web/src/shared/i18n/en.ts`
- Modify: `frontend/web/src/shared/i18n/ru.ts`
- Modify: `frontend/web/src/shared/i18n/zh.ts`

- [x] Add failing page tests for valid import and edit-before-submit, invalid extension, empty/missing-description content, and file read errors.
- [x] Run the targeted page tests and confirm the new cases fail.
- [x] Add a labeled `.txt` file input; validate the extension, read as UTF-8 with `File.text()`, parse, and prefill existing controlled fields without submission.
- [x] Add localized strings for import label/help and invalid type, empty/invalid content, and read failure.
- [x] Run targeted page tests and confirm they pass.

### Task 3: Verification

**Files:** none

- [x] Run `npm test -- --run` from `frontend/web/`; expect all tests to pass.
- [x] Run `npm run lint` from `frontend/web/`; expect no lint errors.
- [x] Run `npm run build` from `frontend/web/`; expect the production build to succeed.
- [x] Run `git diff --check`; expect no whitespace errors.
- [x] Manually compare proposal, scenarios, tasks, and implementation for consistency; check the OpenSpec tasks as each is completed.

## Review Notes

- Независимый read-only review: готово к слиянию; Critical и Important замечаний нет.
- Minor (deferred): при очень быстром выборе двух файлов более медленное чтение первого файла может завершиться после второго и перезаписать поля более старым содержимым. Стоимость ошибки ограничена предсказуемостью формы; можно закрыть счётчиком импорта при следующем UI-проходе.
- Reviewer declined to judge strict rejection of invalid UTF-8 bytes and pre-read file-size limits because the current spec does not define those behaviors.
