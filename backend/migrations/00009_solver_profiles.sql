-- +goose Up
CREATE TABLE solver_profiles (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    triage_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    resolve_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ticket_resolution BIGINT REFERENCES workspace_models(id) ON DELETE SET NULL,
    ticket_triage BIGINT REFERENCES workspace_models(id) ON DELETE SET NULL,
    ticket_resolution_cheap BIGINT REFERENCES workspace_models(id) ON DELETE SET NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (source_id, name)
);

CREATE UNIQUE INDEX solver_profiles_default_idx ON solver_profiles (source_id) WHERE is_default;

INSERT INTO solver_profiles (
    source_id, name, ticket_resolution, ticket_triage, ticket_resolution_cheap, is_default
)
SELECT source.id, 'Default',
    MAX(assignment.model_id) FILTER (WHERE assignment.role = 'ticket_resolution'),
    MAX(assignment.model_id) FILTER (WHERE assignment.role = 'ticket_triage'),
    MAX(assignment.model_id) FILTER (WHERE assignment.role = 'ticket_resolution_cheap'),
    TRUE
FROM sources AS source
LEFT JOIN project_model_assignments AS assignment ON assignment.source_id = source.id
GROUP BY source.id;

CREATE TABLE ticket_runs (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    profile_id BIGINT NOT NULL,
    profile_name TEXT NOT NULL,
    enabled JSONB NOT NULL,
    models JSONB NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX ticket_runs_ticket_idx ON ticket_runs (ticket_id, id);
ALTER TABLE ticket_steps ADD COLUMN run_id BIGINT REFERENCES ticket_runs(id) ON DELETE CASCADE;
ALTER TABLE ticket_steps ADD COLUMN status TEXT NOT NULL DEFAULT 'completed';

-- +goose Down
ALTER TABLE ticket_steps DROP COLUMN status;
ALTER TABLE ticket_steps DROP COLUMN run_id;
DROP TABLE ticket_runs;
DROP TABLE solver_profiles;
