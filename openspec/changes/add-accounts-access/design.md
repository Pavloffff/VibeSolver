# Design: add-accounts-access

## Decisions

- **Auth as SPI** (user decision): `Authenticator` protocol + registry; implementations `noauth-local` and `oauth`. Password/OIDC/LDAP later = new implementation, zero resource-code changes.
- **OAuth is an add-on, not the foundation** (user decision): internal users exist independently; `oauth_identities` is a link table. Sign-in via GitHub/GitLab resolves to an internal user. Pure-internal usage stays first-class.
- **Providers are registry entries**: `github`, `gitlab` ship initially; client credentials from env (`VIBESOLVER_OAUTH_GITHUB_CLIENT_ID/SECRET`, `VIBESOLVER_OAUTH_GITLAB_*`). New provider (gitea…) = registry entry + env, no core changes.
- **Sessions**: short-lived signed tokens (JWT, HS256; secret from env `VIBESOLVER_SESSION_SECRET`), issued after OAuth callback. Local mode: no tokens at all (noauth-local).
- **Git-role inheritance** (user decision): project linked to a git repo; provider API is queried for the user's role on the repo (GitHub `GET /repos/{owner}/{repo}/collaborators/{user}`; GitLab `GET /projects/{id}/members/{uid}`); mapping registry decides access level. Negative results cached briefly (TTL from env) to avoid hammering provider APIs.
- **Projects**: UUID internal ids; sources get nullable `project_id` (ungrouped sources remain valid — backward compat with the current import flow).
- **RBAC scope now**: admin superrole + git-role inheritance only (user decision); granular roles are a later change — access levels are stored as data (registry mapping), not enum columns.

## Risks / Trade-offs

- Provider API rate limits on role checks → short TTL cache + eager refresh on 403.
- OAuth client secrets live in env; local mode never requires them.
- JWT revocation is coarse (short TTL instead of deny-list) — acceptable for MVP.