"""
S2: Test that *_af sources now use addis_fortune adapter with slug configuration.

This test verifies the fix for wasteful double-run pattern where *_af sources
caused intentional KeyError → 2 DB runs (1 failed + 1 fallback).

After S2:
- adapter_key changed from 'oromia_af' to 'addis_fortune'
- slug stored in adapter_config JSON column
- 1 run per collection (not 2)
"""

import pytest
import psycopg2
import os
from infrastructure.adapter_registry_v2 import default_registry
from scheduler.runner import _parse


def test_addis_fortune_adapter_registered():
    """addis_fortune adapter is now registered in adapter_registry."""
    assert default_registry.is_registered("addis_fortune")
    
    adapter = default_registry.get("addis_fortune")
    assert adapter is not None


def test_addis_fortune_parse_requires_slug():
    """addis_fortune parse() requires slug parameter."""
    from adapters.banks.addis_fortune import parse
    
    test_html = "<html><body>test</body></html>"
    
    # Without slug, should raise ValueError
    with pytest.raises(ValueError, match="requires 'slug' parameter"):
        parse(test_html)


def test_addis_fortune_parse_with_slug():
    """addis_fortune parse() works with slug parameter."""
    from adapters.banks.addis_fortune import parse
    
    test_html = "<html><body>test</body></html>"
    
    # With slug, should not raise (may return errors from parse failure)
    result = parse(test_html, slug="oromia-international-bank-sc")
    
    # Result should be ParseResult with errors (no valid data in test HTML)
    assert hasattr(result, "records")
    assert hasattr(result, "errors")


def test_runner_parse_with_adapter_config():
    """runner._parse() passes adapter_config to adapter."""
    adapter = default_registry.get("addis_fortune")
    test_html = "<html><body>test</body></html>"
    adapter_config = {"slug": "oromia-international-bank-sc"}
    
    records, errors, warnings = _parse(adapter, test_html, "cash", adapter_config)
    
    # Should execute without raising
    assert isinstance(records, list)
    assert isinstance(errors, list)
    assert isinstance(warnings, list)


def test_migration_004_applied():
    """Migration 004 has been applied to database."""
    dsn = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
    
    try:
        conn = psycopg2.connect(dsn)
    except Exception:
        pytest.skip("Cannot connect to database")
        return
    
    try:
        cur = conn.cursor()
        
        # Check adapter_config column exists
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'rate_source' AND column_name = 'adapter_config'
        """)
        
        assert cur.fetchone() is not None, "adapter_config column not found"
        
        # Check 4 sources have been updated
        cur.execute("""
            SELECT id, adapter_key, adapter_config->>'slug' as slug
            FROM rate_source
            WHERE adapter_key = 'addis_fortune' 
              AND adapter_config IS NOT NULL
            ORDER BY id
        """)
        
        rows = cur.fetchall()
        assert len(rows) == 4, f"Expected 4 addis_fortune sources, found {len(rows)}"
        
        # Verify specific sources
        expected = {
            49: "oromia-international-bank-sc",
            60: "anbesa-bank-1",
            62: "hijra-bank-sc",
            63: "national-bank-of-ethiopia",
        }
        
        for row in rows:
            source_id, adapter_key, slug = row
            assert adapter_key == "addis_fortune"
            assert slug == expected[source_id], f"Source {source_id} has wrong slug: {slug}"
        
    finally:
        conn.close()


def test_no_af_keys_in_database():
    """Old *_af adapter keys should no longer exist in database."""
    dsn = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
    
    try:
        conn = psycopg2.connect(dsn)
    except Exception:
        pytest.skip("Cannot connect to database")
        return
    
    try:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT adapter_key, COUNT(*) 
            FROM rate_source
            WHERE adapter_key IN ('oromia_af', 'anbesa_af', 'hijra_af', 'nbe_af')
            GROUP BY adapter_key
        """)
        
        rows = cur.fetchall()
        
        if rows:
            af_keys = ", ".join(f"{row[0]} ({row[1]})" for row in rows)
            pytest.fail(f"Found *_af keys still in database: {af_keys}")
        
    finally:
        conn.close()


def test_schema_fingerprint_with_slug():
    """schema_fingerprint() also accepts slug parameter."""
    from adapters.banks.addis_fortune import schema_fingerprint
    
    test_html = "<html><body>test</body></html>"
    
    # Should work with slug
    fp = schema_fingerprint(test_html, slug="oromia-international-bank-sc")
    assert isinstance(fp, str)
    assert len(fp) > 0
    
    # Should raise without slug
    with pytest.raises(ValueError, match="requires 'slug' parameter"):
        schema_fingerprint(test_html)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
