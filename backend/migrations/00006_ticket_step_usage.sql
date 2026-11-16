-- +goose Up
ALTER TABLE ticket_steps ADD COLUMN tokens_in INT;
ALTER TABLE ticket_steps ADD COLUMN tokens_out INT;
ALTER TABLE ticket_steps ADD COLUMN cost_usd NUMERIC(12, 6);

-- +goose Down
ALTER TABLE ticket_steps DROP COLUMN cost_usd;
ALTER TABLE ticket_steps DROP COLUMN tokens_out;
ALTER TABLE ticket_steps DROP COLUMN tokens_in;
