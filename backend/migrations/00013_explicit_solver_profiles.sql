-- +goose Up
ALTER TABLE solver_profiles ADD COLUMN is_archived_seed BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE solver_profiles AS profile
SET is_archived_seed = TRUE
WHERE profile.is_default
  AND profile.name = 'Default'
  AND profile.triage_enabled
  AND profile.resolve_enabled
  AND profile.ticket_resolution IS NULL
  AND profile.ticket_triage IS NULL
  AND profile.ticket_resolution_cheap IS NULL
  AND profile.specialist_flags = '{}'::jsonb
  AND NOT EXISTS (SELECT 1 FROM ticket_runs AS run WHERE run.profile_id = profile.id);

-- +goose Down
UPDATE solver_profiles AS profile
SET is_default = TRUE
FROM (
    SELECT source_id, MIN(id) AS id
    FROM solver_profiles
    GROUP BY source_id
    HAVING NOT BOOL_OR(is_default)
) AS first_profile
WHERE profile.id = first_profile.id;

ALTER TABLE solver_profiles DROP COLUMN is_archived_seed;
