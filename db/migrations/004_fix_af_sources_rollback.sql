-- Rollback for Migration 004: Restore *_af adapter keys
--
-- This restores the original behavior where *_af sources trigger KeyError
-- and use the fallback mechanism.

BEGIN;

-- Step 1: Restore original adapter_key values
UPDATE rate_source 
SET 
    adapter_key = 'oromia_af',
    adapter_config = NULL
WHERE id = 49 AND adapter_key = 'addis_fortune' 
  AND adapter_config->>'slug' = 'oromia-international-bank-sc';

UPDATE rate_source 
SET 
    adapter_key = 'anbesa_af',
    adapter_config = NULL
WHERE id = 60 AND adapter_key = 'addis_fortune' 
  AND adapter_config->>'slug' = 'anbesa-bank-1';

UPDATE rate_source 
SET 
    adapter_key = 'hijra_af',
    adapter_config = NULL
WHERE id = 62 AND adapter_key = 'addis_fortune' 
  AND adapter_config->>'slug' = 'hijra-bank-sc';

UPDATE rate_source 
SET 
    adapter_key = 'nbe_af',
    adapter_config = NULL
WHERE id = 63 AND adapter_key = 'addis_fortune' 
  AND adapter_config->>'slug' = 'national-bank-of-ethiopia';

-- Step 2: Drop adapter_config column
ALTER TABLE rate_source 
DROP COLUMN adapter_config;

-- Step 3: Verify rollback
DO $$
DECLARE
    af_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO af_count
    FROM rate_source
    WHERE adapter_key IN ('oromia_af', 'anbesa_af', 'hijra_af', 'nbe_af');
    
    IF af_count <> 4 THEN
        RAISE EXCEPTION 'Expected 4 *_af sources after rollback, found %', af_count;
    END IF;
    
    RAISE NOTICE 'Rollback 004: Successfully restored 4 *_af adapter keys';
END $$;

COMMIT;
