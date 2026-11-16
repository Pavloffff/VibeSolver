-- +goose Up
CREATE TABLE tickets (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    triage_json JSONB,
    answer TEXT,
    escalate_reason TEXT,
    citations_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX tickets_source_created_idx ON tickets (source_id, created_at DESC);

CREATE TABLE ticket_steps (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_id BIGINT,
    duration_ms INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ticket_steps_ticket_idx ON ticket_steps (ticket_id, id);

-- +goose Down
DROP TABLE ticket_steps;
DROP TABLE tickets;
