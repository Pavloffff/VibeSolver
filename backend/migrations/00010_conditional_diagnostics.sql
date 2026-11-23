-- +goose Up
ALTER TABLE solver_profiles ADD COLUMN specialist_flags JSONB NOT NULL DEFAULT '{}';
ALTER TABLE sources ADD COLUMN diagnostic_ui_probe TEXT, ADD COLUMN diagnostic_web_provider TEXT;
ALTER TABLE tickets ADD COLUMN use_web_search BOOLEAN NOT NULL DEFAULT FALSE, ADD COLUMN ui_observation JSONB;

-- +goose Down
ALTER TABLE tickets DROP COLUMN ui_observation, DROP COLUMN use_web_search;
ALTER TABLE sources DROP COLUMN diagnostic_web_provider, DROP COLUMN diagnostic_ui_probe;
ALTER TABLE solver_profiles DROP COLUMN specialist_flags;
