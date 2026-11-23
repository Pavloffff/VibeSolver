-- +goose Up
ALTER TABLE sources ADD COLUMN allow_web_search boolean NOT NULL DEFAULT false;
ALTER TABLE ticket_runs ADD COLUMN rerun_context jsonb;

-- +goose Down
ALTER TABLE ticket_runs DROP COLUMN rerun_context;
ALTER TABLE sources DROP COLUMN allow_web_search;
