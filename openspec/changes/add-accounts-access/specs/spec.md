# Spec: internal-accounts

## ADDED Requirements

### Requirement: internal user record

The system SHALL maintain `users` (internal UUID id, display_name, is_admin, created_at). Creating users SHALL be possible without any external identity.

### Requirement: local default user

In local mode the system SHALL transparently use a default local user (auto-created on first run); the user SHALL NOT be asked to log in (user convenience). Switching local mode to a real auth module later SHALL NOT require data migration beyond linking the default user.

# Spec: oauth-federation

## ADDED Requirements

### Requirement: linked identities

A user MAY have zero or more linked `oauth_identities` (provider, provider_uid, provider_username, linked_at). OAuth is an add-on: all product features SHALL work for a user with no linked identity.

### Requirement: provider registry

OAuth providers SHALL be registered entries (github, gitlab initially) with per-provider config (client id/secret from env); adding a provider SHALL NOT require core code changes.

#### Scenario: sign in via GitHub

- **GIVEN** server mode with GitHub provider configured (env: client id/secret)
- **WHEN** a user clicks "Sign in with GitHub" and completes the OAuth flow
- **THEN** the system finds or creates the internal user by provider_uid and establishes a session

#### Scenario: existing account linking

- **GIVEN** an internal user without linked identities
- **WHEN** they complete OAuth sign-in with a GitHub account
- **THEN** the identity is linked to the existing internal user (by explicit linking flow), not a duplicate account

# Spec: projects

## ADDED Requirements

### Requirement: projects

The system SHALL maintain `projects` (internal id, name, description, timestamps). Sources MAY be grouped under a project (`sources.project_id`, nullable). A project MAY carry one linked git repository reference (provider key + external repo/project id).

# Spec: git-role-inheritance

## ADDED Requirements

### Requirement: inherited access

For a project linked to a git repository, an authenticated user who holds a role in that repository (collaborator on GitHub; any role on GitLab) SHALL get access to the project in VibeSolver without explicit sharing. The provider-role → access-level mapping SHALL be a registry (extensible per provider).

#### Scenario: GitHub collaborator gains access

- **GIVEN** project P linked to GitHub repo owner/name, user U signed in via GitHub with uid that is a collaborator of owner/name
- **WHEN** U opens P
- **THEN** access is granted (level per the role mapping)

### Requirement: admin superrole

Users with `is_admin=true` SHALL have access to all projects and settings regardless of git roles.

# Spec: auth-spi

## ADDED Requirements

### Requirement: pluggable authentication

The system SHALL define an `Authenticator` interface (authenticate request → user or null) with implementations: `noauth-local` (active in local mode) and `oauth` (server mode). Adding a password/OIDC/LDAP authenticator later SHALL NOT require changes to resource endpoints.

# Spec: api-auth

## ADDED Requirements

### Requirement: auth middleware

All resource endpoints SHALL pass through the authenticator: local mode uses noauth-local (zero friction); server mode requires a session/bearer token from the OAuth flow. The list of protected endpoints is centralized, not scattered decorators.

### Requirement: minimal account UI

The UI SHALL show the current user, offer OAuth sign-in buttons for configured providers (server mode only), and include a project switcher. Local mode shows the local user without login screens.