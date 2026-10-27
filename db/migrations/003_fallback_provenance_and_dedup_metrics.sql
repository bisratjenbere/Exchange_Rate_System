ALTER TABLE collection_run
ADD COLUMN IF NOT EXISTS records_duplicated INT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS is_fallback BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS fallback_adapter VARCHAR(50);

ALTER TABLE rate_observation
ADD COLUMN IF NOT EXISTS is_fallback BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_rate_observation_current_source_curr
ON rate_observation (source_id, source_currency_code, is_current);
