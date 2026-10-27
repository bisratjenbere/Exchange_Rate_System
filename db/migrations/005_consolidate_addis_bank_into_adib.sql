UPDATE rate_observation SET is_current = FALSE WHERE source_id = (SELECT id FROM rate_source WHERE adapter_key = 'addis_bank_af');
UPDATE rate_observation SET source_id = (SELECT id FROM rate_source WHERE adapter_key = 'adib_api') WHERE source_id = (SELECT id FROM rate_source WHERE adapter_key = 'addis_bank_af');
UPDATE change_candidate SET source_id = (SELECT id FROM rate_source WHERE adapter_key = 'adib_api') WHERE source_id = (SELECT id FROM rate_source WHERE adapter_key = 'addis_bank_af');
UPDATE source_alert SET source_id = (SELECT id FROM rate_source WHERE adapter_key = 'adib_api') WHERE source_id = (SELECT id FROM rate_source WHERE adapter_key = 'addis_bank_af');
UPDATE collection_run SET source_id = (SELECT id FROM rate_source WHERE adapter_key = 'adib_api') WHERE source_id = (SELECT id FROM rate_source WHERE adapter_key = 'addis_bank_af');
DELETE FROM rate_source WHERE adapter_key = 'addis_bank_af';
DELETE FROM bank WHERE code = 'ADDIS_BANK';
UPDATE rate_observation SET is_current = FALSE WHERE source_id = (SELECT id FROM rate_source WHERE adapter_key = 'adib_api') AND is_current = TRUE AND effective_date < CURRENT_DATE - 3;
