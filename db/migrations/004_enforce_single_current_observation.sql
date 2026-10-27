WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY source_id, source_currency_code, category_id
               ORDER BY effective_date DESC NULLS LAST,
                        COALESCE(version_number, 0) DESC,
                        id DESC
           ) as rn
    FROM rate_observation
    WHERE is_current = TRUE
)
UPDATE rate_observation
SET is_current = FALSE
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

CREATE UNIQUE INDEX IF NOT EXISTS uq_one_current_per_source_currency_category
ON rate_observation (source_id, source_currency_code, category_id) NULLS NOT DISTINCT
WHERE is_current = TRUE;
