-- Migration 006: recompute fingerprints to version 3
--
-- Decision D-1 Option A: backfill all existing rows before deploying new
-- fingerprint code. Run scripts/backfill_fingerprints.py after applying
-- this migration and before deploying the updated pipeline/fingerprint.py.
--
-- The backup table preserves old v2 fingerprints for deterministic rollback.

CREATE TABLE IF NOT EXISTS fingerprint_backup_v2 (
    observation_id  BIGINT PRIMARY KEY REFERENCES rate_observation(id),
    old_fingerprint CHAR(64),
    old_version     SMALLINT,
    backed_up_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
