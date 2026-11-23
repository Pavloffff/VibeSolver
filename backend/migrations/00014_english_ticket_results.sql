-- +goose Up
ALTER TABLE tickets ADD COLUMN english_result TEXT;

UPDATE tickets AS ticket
SET english_result = COALESCE(
    ticket.localized_result ->> 'en',
    CASE WHEN EXISTS (
        SELECT 1
        FROM ticket_runs AS run
        JOIN ticket_steps AS step ON step.run_id = run.id AND step.ticket_id = ticket.id
        WHERE run.id = (SELECT MAX(id) FROM ticket_runs WHERE ticket_id = ticket.id)
          AND run.status = ticket.status
          AND run.finished_at IS NOT NULL
          AND step.step = CASE ticket.status WHEN 'answered' THEN 'answer' ELSE 'escalate' END
          AND step.output_json ->> 'localization_status' IN ('completed', 'failed')
    ) THEN
        CASE ticket.status WHEN 'answered' THEN ticket.answer ELSE ticket.escalate_reason END
    END
)
WHERE ticket.status IN ('answered', 'escalated');

-- +goose Down
ALTER TABLE tickets DROP COLUMN english_result;
