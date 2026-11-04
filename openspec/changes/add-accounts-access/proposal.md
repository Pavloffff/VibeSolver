# Proposal: add-accounts-access

## Why

VibeSolver is a collaborative product: support teams work on the same product's knowledge base. Before the model-import phase (chunking/embeddings — the most expensive asset in the system), we need identity and access boundaries: who owns a project, who can register sources, who can read the indexed knowledge. Without accounts, every imported byte is effectively public to anyone with network access.

## What Changes

### Capability: internal-accounts

Minimal internal identity: `users` table (internal id, display name, is_admin, created_at). No passwords yet — authentication is an extension point (see auth-spi). The current local single-user flow keeps working: the local mode auto-creates/uses a default local user; no login friction (user convenience philosophy).

### Capability: oauth-federation (GitHub + GitLab as ADD-ONS)

OAuth login via GitHub and GitLab as an ADD-ON to internal accounts (user decision): a user may link one or more `oauth_identities` (provider key, provider uid, username) to their internal account and sign in through them. Pure-internal (no OAuth) usage remains fully supported. Providers are registry entries (not a hardcoded set) — a new provider (Gitea, Bitbucket) is a config/registry addition.

### Capability: projects

`projects` table: internal project id (UUID), name, description, timestamps. Sources are grouped under projects (source gains a nullable `project_id` now; enforced later). A project can be linked to a GitHub repo / GitLab project (provider, external id) — this powers git-role inheritance.

### Capability: git-role-inheritance

Access to a linked project SHALL be inherited from the linked git repository roles (user decision: "admin + inheritance from git roles"): a user authenticated via a provider who is a collaborator/maintainer/etc. of the linked repo gets access to the corresponding VibeSolver project without explicit sharing. Internal `is_admin` remains the system-level superrole. Role mapping is a registry (provider role → VS access level), extensible per provider.

### Capability: auth-spi

Authentication is a pluggable mechanism (extension point): the system defines an `Authenticator` interface (verify request → user id) with two implementations now: `noauth-local` (local single-user mode) and `oauth` (GitHub/GitLab). A ready-made auth module (password-based, LDAP, OIDC) can be added later without touching resource code.

### Capability: api-auth

API endpoints get an auth middleware: local mode → noauth; server mode → Bearer/OAuth session. Frontend adds a minimal account UI: display current user, OAuth sign-in buttons (server mode), project switcher.

## Capabilities with no changes

- Roles beyond admin + git-inheritance (granular RBAC — later, when product needs it).
- Team/organization management — later.

## Impact

- DB: new migrations (users, oauth_identities, projects, source.project_id).
- API: auth middleware; new /auth and /projects endpoints.
- UI: account section, OAuth sign-in, project switcher.
- Existing source-import flow keeps working unchanged in local mode.