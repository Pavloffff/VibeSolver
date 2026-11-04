# Tasks: add-accounts-access

## 1. Data model

- [ ] 1.1 `кодер`: goose migration — `users` (uuid pk, display_name, is_admin, created_at), `oauth_identities` (user_id fk, provider, provider_uid, provider_username, linked_at, unique(provider, provider_uid)), `projects` (uuid pk, name, description, created_at), `sources.project_id` (nullable fk)
- [ ] 1.2 `тестер`: migration round-trip tests (up/down on temp PG)

## 2. Auth SPI + local mode (tests first)

- [ ] 2.1 `тестер`: Authenticator contract tests — noauth-local returns default user; unknown request → null
- [ ] 2.2 `кодер`: `Authenticator` protocol + registry; `noauth-local` implementation; default local user bootstrap on first request (local mode); FastAPI middleware wiring (centralized dependency)
- [ ] 2.3 `тестер`: existing endpoints still work in local mode after middleware (regression)

## 3. OAuth federation (tests first)

- [ ] 3.1 `тестер`: OAuth flow tests with stubbed provider (state/nonce validation, error paths: denied, bad code)
- [ ] 3.2 `кодер`: provider registry (github, gitlab; client id/secret from env `VIBESOLVER_OAUTH_<PROVIDER>_*`), /auth/<provider>/start + /auth/<provider>/callback endpoints, session tokens (signed, secret from env), find-or-create user by identity, link-identity flow for existing user
- [ ] 3.3 `тестер`: git-role inheritance tests — stubbed GitHub API (collaborator check) / GitLab API (project member check) → access granted/denied matrix

## 4. Projects + access control (tests first)

- [ ] 4.1 `тестер`: project CRUD tests + access matrix (admin ok, linked-git collaborator ok, stranger 403)
- [ ] 4.2 `кодер`: projects CRUD endpoints; role-mapping registry (provider role → access level); access check service used by endpoints; sources.project_id assignment endpoint
- [ ] 4.3 `тестер`: e2e in server mode — OAuth stub login → create project → link repo (stubbed) → second stub user (collaborator) gets access, third (stranger) doesn't

## 5. UI

- [ ] 5.1 `кодер`: account section (current user, provider buttons per GET /auth/providers), project switcher, project CRUD minimal screen
- [ ] 5.2 i18n keys (en/ru/zh) for all new UI; tests for sign-in screen rendering

## 6. Review + integration

- [ ] 6.1 `ревьюер`: security review (token handling, state validation, secrets from env only, no tokens in logs), spec compliance
- [ ] 6.2 Fix findings; full checks (pytest, ruff, mypy, lint, vitest, build); README note (accounts section in docs/running.md)
- [ ] 6.3 Update docs; archive change