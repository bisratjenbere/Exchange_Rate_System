-- Migration 002: Add failure tracking and alert system
-- Adds consecutive_failures, last_failure_code, last_failure_at, and alert_sent_at to rate_source
-- Creates source_alert table for tracking alerts

-- Add failure tracking columns to rate_source table
ALTER TABLE rate_source
ADD COLUMN consecutive_failures INT NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
ADD COLUMN last_failure_code VARCHAR(50),
ADD COLUMN last_failure_at TIMESTAMPTZ,
ADD COLUMN alert_sent_at TIMESTAMPTZ;

-- Create source_alert table for tracking alerts sent
CREATE TABLE source_alert (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES rate_source(id),
    error_code VARCHAR(50) NOT NULL,
    summary TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT
);

-- Index for querying alerts by source
CREATE INDEX idx_alert_source_created ON source_alert (source_id, created_at DESC);

-- Index for finding unacknowledged alerts
CREATE INDEX idx_alert_unacknowledged ON source_alert (acknowledged_at)
WHERE acknowledged_at IS NULL;

-- Comments for documentation
COMMENT ON COLUMN rate_source.consecutive_failures IS 'Number of consecutive failed collection runs';
COMMENT ON COLUMN rate_source.last_failure_code IS 'Error code from most recent failure (http_failure, parse_failure, schema_change)';
COMMENT ON COLUMN rate_source.last_failure_at IS 'Timestamp of most recent failure';
COMMENT ON COLUMN rate_source.alert_sent_at IS 'Timestamp when alert was last sent (prevents spam)';
COMMENT ON TABLE source_alert IS 'Alert log for sources with consecutive failures';
