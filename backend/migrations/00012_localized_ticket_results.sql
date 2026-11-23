-- +goose Up
ALTER TABLE tickets ADD COLUMN localized_result jsonb;

-- +goose Down
ALTER TABLE tickets DROP COLUMN localized_result;
