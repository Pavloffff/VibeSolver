-- +goose Up
ALTER TABLE ticket_log_attachments
    ADD COLUMN embedding_model_id BIGINT REFERENCES workspace_models(id) ON DELETE SET NULL;

CREATE INDEX ticket_log_attachments_embedding_model_idx
    ON ticket_log_attachments (source_id, ticket_id, embedding_model_id)
    WHERE status = 'ready';

-- +goose Down
DROP INDEX ticket_log_attachments_embedding_model_idx;
ALTER TABLE ticket_log_attachments DROP COLUMN embedding_model_id;
