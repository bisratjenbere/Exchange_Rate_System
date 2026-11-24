-- Migration 007: Add collection_control table
-- Purpose: Allow pausing/resuming scheduler without code changes
-- Date: 2024-11-23
-- Idempotent: Can be run multiple times safely

CREATE TABLE IF NOT EXISTS collection_control (
    id SERIAL PRIMARY KEY,
    paused BOOLEAN DEFAULT FALSE,
    paused_at TIMESTAMPTZ,
    paused_by TEXT,
    reason TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ensure single row exists (singleton pattern)
INSERT INTO collection_control (id, paused)
SELECT 1, FALSE
WHERE NOT EXISTS (SELECT 1 FROM collection_control WHERE id = 1);

-- Note: Singleton constraint not enforced at DB level for simplicity.
-- Application code (scheduler/control.py) manages single-row invariant.
