-- Migration 004: Fix *_af sources to use addis_fortune adapter with slug configuration
-- 
-- Problem: 
--   4 sources (oromia_af, anbesa_af, hijra_af, nbe_af) use adapter keys that are
--   NOT registered in adapter_registry. This causes intentional KeyError which triggers
--   fallback mechanism, creating 2 DB runs per collection (1 failed + 1 fallback).
--
-- Solution:
--   Change adapter_key to 'addis_fortune' and store slug in new adapter_config column.
--   The addis_fortune adapter will be enhanced to accept slug parameter.
--
-- Impact:
--   - Reduces DB writes: 2 runs → 1 run per collection
--   - Eliminates failed runs for these sources
--   - Clearer intent: sources explicitly use addis_fortune
--
-- Rollback: See 004_fix_af_sources_rollback.sql

BEGIN;

-- Step 1: Add adapter_config column to store per-source adapter configuration
ALTER TABLE rate_source 
ADD COLUMN adapter_config JSONB;

COMMENT ON COLUMN rate_source.adapter_config IS 
'JSON configuration for adapter behavior. Example: {"slug": "bank-name"} for addis_fortune adapter';

-- Step 2: Update the 4 *_af sources to use addis_fortune adapter with slug config
UPDATE rate_source 
SET 
    adapter_key = 'addis_fortune',
    adapter_config = jsonb_build_object('slug', 'oromia-international-bank-sc')
WHERE id = 49 AND adapter_key = 'oromia_af';

UPDATE rate_source 
SET 
    adapter_key = 'addis_fortune',
    adapter_config = jsonb_build_object('slug', 'anbesa-bank-1')
WHERE id = 60 AND adapter_key = 'anbesa_af';

UPDATE rate_source 
SET 
    adapter_key = 'addis_fortune',
    adapter_config = jsonb_build_object('slug', 'hijra-bank-sc')
WHERE id = 62 AND adapter_key = 'hijra_af';

UPDATE rate_source 
SET 
    adapter_key = 'addis_fortune',
    adapter_config = jsonb_build_object('slug', 'national-bank-of-ethiopia')
WHERE id = 63 AND adapter_key = 'nbe_af';

-- Step 3: Verify changes
DO $$
DECLARE
    af_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO af_count
    FROM rate_source
    WHERE adapter_key = 'addis_fortune' 
      AND adapter_config IS NOT NULL
      AND adapter_config->>'slug' IS NOT NULL;
    
    IF af_count <> 4 THEN
        RAISE EXCEPTION 'Expected 4 addis_fortune sources with slug config, found %', af_count;
    END IF;
    
    RAISE NOTICE 'Migration 004: Successfully updated 4 sources to use addis_fortune adapter';
END $$;

COMMIT;
