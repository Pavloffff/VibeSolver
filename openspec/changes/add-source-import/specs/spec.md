# Spec: source-registry

## ADDED Requirements

### Requirement: register a source via API

The system SHALL expose `POST /api/v1/sources` accepting `{type, name, config}`. `type` MUST be a key present in the connector registry (validation is registry-driven, not a hardcoded list — new connectors extend the accepted set without API changes). The system SHALL validate config via the connector's `validate_config` before persisting.

#### Scenario: valid git source

- **GIVEN** no sources registered
- **WHEN** `POST /api/v1/sources` with `{"type": "git", "name": "main repo", "config": {"url": "https://github.com/x/y.git", "branch": "main"}}`
- **THEN** the response is 201 with the created source `id`, and the source appears in `GET /api/v1/sources`

#### Scenario: invalid config rejected

- **GIVEN** connector `git` requires `url`
- **WHEN** `POST /api/v1/sources` with `{"type": "git", "config": {}}`
- **THEN** the response is 422 with a validation error message, and nothing is persisted

### Requirement: list and delete sources

The system SHALL expose `GET /api/v1/sources` (list with last import status) and `DELETE /api/v1/sources/{id}` (soft delete: `enabled=false` + hidden from list).

#### Scenario: list shows import status

- **GIVEN** source id=1 with last import finished successfully
- **WHEN** `GET /api/v1/sources`
- **THEN** each item includes `id, name, type, enabled, last_import: {status, finished_at}`

### Requirement: import trigger

The system SHALL expose `POST /api/v1/sources/{id}/import` that enqueues a Celery import task and returns 202 with `task_id`. The UI SHALL show import progress by polling `GET /api/v1/sources/{id}/import` (latest import: `status, progress, error`).

#### Scenario: enqueue import

- **GIVEN** registered source id=1 (git)
- **WHEN** `POST /api/v1/sources/1/import`
- **THEN** response is 202 `{task_id}`, and `GET /api/v1/sources/1/import` eventually reports `status=done`

# Spec: source-connector-spi

## ADDED Requirements

### Requirement: connector interface

Every source connector MUST implement the protocol: `validate_config(config: dict) -> None` (raise on invalid) and `fetch_snapshot(config: dict) -> Iterator[RawItem]` where `RawItem` has `path: str`, `content: bytes`, `meta: dict`.

### Requirement: connector registry

The system SHALL keep a registry mapping type key → connector class. `list_connectors()` SHALL return all registered types with a `ready: bool` flag (False for skeletons).

### Requirement: registry introspection endpoint

The system SHALL expose `GET /api/v1/connectors` returning the registry contents: `[{type, ready, config_schema}]`. The UI registration form SHALL be generated from this response; the frontend MUST NOT hardcode the type list.

#### Scenario: new connector appears in UI

- **GIVEN** connector `gitea` registered server-side with `ready: true` and its config schema
- **WHEN** the user opens the source registration form
- **THEN** `gitea` is selectable with its config fields rendered from `config_schema`, without any frontend code change

# Spec: git-connector

## ADDED Requirements

### Requirement: git snapshot fetch

The git connector SHALL clone the repository with `--depth 1` into a temp dir, checkout the configured branch, and yield every non-ignored text file as RawItem (binary files excluded by extension list; `.gitignore` rules respected).

#### Scenario: import a public repo

- **GIVEN** source config `{"url": "<any public git url>", "branch": "main"}`
- **WHEN** import task runs
- **THEN** all tracked text files are yielded with correct relative paths, and the temp dir is removed afterwards

### Requirement: token handling

Private-repo tokens SHALL be passed via config `token_ref` (name of a secret stored server-side), never logged, never returned by API responses.

# Spec: local-folder-connector

## ADDED Requirements

### Requirement: folder walk

The local-folder connector SHALL recursively walk the configured path and yield every non-excluded text file as RawItem, using the same exclusion rules as git-connector.

#### Scenario: import a folder

- **GIVEN** config `{"path": "D:/some/project"}`
- **WHEN** import task runs
- **THEN** all text files under the path are yielded with paths relative to the root

# Spec: svn-mercurial-connector-skeletons

## ADDED Requirements

### Requirement: skeletons

The system SHALL provide svn and hg connectors that: validate config shape, are listed in the registry with `ready: false`, and raise `NotImplementedError` from `fetch_snapshot`.

# Spec: import-pipeline

## ADDED Requirements

### Requirement: stage-based pipeline

The import SHALL run as an ordered pipeline of stages from a stage registry: **fetch** (connector yields RawItems) → **persist** (raw files to SeaweedFS, rows to Postgres). The pipeline SHALL accept additional transform stages registered between fetch and persist without worker changes (empty in this change — future chunking/embedding/docstring stages).

### Requirement: persist snapshot

The persist stage SHALL upload each RawItem to SeaweedFS (S3 API, bucket `raw`) and insert an `imported_files` row (source_id, path, size, storage_key, content_hash). A completed import SHALL set the source's `last_import` status.

### Requirement: idempotency

Re-importing the same source SHALL re-fetch and overwrite (upsert by source_id + path, keyed on content_hash — unchanged files are not re-uploaded).

# Spec: infra-local-remote

## ADDED Requirements

### Requirement: two run modes

The desktop/web app SHALL support mode selection on first run: **local** (docker-compose services started in background) or **remote** (API base URL + credentials). The choice SHALL be persisted and changeable in settings.

#### Scenario: local mode first run

- **GIVEN** fresh install on a machine with Docker
- **WHEN** user picks "local"
- **THEN** infra containers start in background, and the app connects to `http://localhost:<api-port>`

#### Scenario: remote mode

- **GIVEN** existing server deployment
- **WHEN** user picks "remote" and enters the server URL
- **THEN** the app skips local infra and calls the remote API

### Requirement: seaweedfs stack

The local infra SHALL run SeaweedFS as `chrislusf/seaweedfs:4.17` services master/volume/filer/s3 (pattern proven in the reference deployment), with an S3 bucket `raw` auto-created at startup.

# Spec: ui-i18n

## ADDED Requirements

### Requirement: localized UI

All user-facing strings in web and desktop UIs SHALL be resolved through a translation dictionary (`en`, `ru`, `zh`). The default language SHALL be English. The user SHALL be able to change the language in Settings; the choice SHALL be persisted (localStorage / desktop config) and applied without restart.

#### Scenario: switch language

- **GIVEN** UI running with default language `en`
- **WHEN** the user selects «Русский» in Settings
- **THEN** all UI texts switch to Russian immediately and remain Russian after app restart

### Requirement: dictionary extensibility

Adding a new language SHALL require only a new dictionary file — no component changes. Dictionaries live in `frontend/web/src/i18n/` and are the single source of UI text.

# Spec: desktop-app

## ADDED Requirements

### Requirement: electron packaging

The desktop app SHALL be an Electron wrapper around the same React UI codebase as `apps/web`, packaged as executables for Windows, Linux, and macOS via a build script in `scripts/`.

### Requirement: ui feature parity

The desktop app SHALL render the identical web UI (source registration form, source list with import status, mode settings). No feature shall be web-only or desktop-only.