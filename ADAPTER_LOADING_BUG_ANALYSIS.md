# Adapter Loading Bug - Complete Analysis

**Date**: October 21, 2026  
**Bug**: `_load_adapter()` incorrectly returned `AddisFortuneAdapter` for 30+ banks

---

## Root Cause

The `_load_adapter()` function in `scheduler/runner.py` had this logic:

```python
def _load_adapter(adapter_key: str):
    from adapters.addis_fortune.adapter import get_adapter_for_key, AF_SLUG_MAP
    # BUG: Checks ALL keys in AF_SLUG_MAP, not just AF-only keys
    if adapter_key in AF_SLUG_MAP:
        af = get_adapter_for_key(adapter_key)
        if af is not None:
            return af  # Returns AddisFortuneAdapter!
    # ... rest of logic to load dedicated adapter
```

**Problem**: This returned `AddisFortuneAdapter` for ANY adapter_key in `AF_SLUG_MAP`, which includes 30+ banks that HAVE their own dedicated adapters. AddisFortuneAdapter expects Livewire JSON format, so it returned 0 records when fed regular HTML/JSON from other banks.

---

## Affected Banks (30 banks with dedicated adapters)

All these banks have their own adapters but were being routed to AddisFortuneAdapter:

### ✅ NOW WORKING (Have Oct 21 Data After Fix)

| Bank | Adapter Key | Oct 21 Records | Notes |
|------|-------------|----------------|-------|
| CBE | cbe_api | 96 | Commercial Bank of Ethiopia |
| Dashen | dashen_html | 22 | ✅ |
| BOA | boa_html | 21 | Bank of Abyssinia |
| Amhara | amhara_html | 31 | Last effective date: Oct 20 |
| DBE | dbe_html | 19 | Development Bank of Ethiopia |
| Bunna | bunna_html | 16 | ✅ |
| NIB | nib_html | 16 | **Also had HTML structure change** |
| Awash | awash_ajax | 15 | ✅ |
| ZamZam | zamzam_html | 15 | ✅ |
| Zemen | zemen_ajax | 24 | ✅ |
| Hibret | hibret_html | 19 | ✅ |
| Abay | abay_html | 18 | ✅ |
| Siket | siket_html | 17 | ✅ |
| Tsedey | tsedey_html | 24 | ✅ |
| Wegagen | wegagen_api | 10 | Last effective date: Oct 20 |
| ADIB | adib_api | 9 | Addis International Bank, Oct 20 |
| Goh Betoch | goh_betoch_html | 8 | Last effective date: Oct 20 |
| Gadaa | gadaa_api | 7 | ✅ |
| Berhan | berhan_html | 6 | ✅ |
| Enat | enat_html | 6 | ✅ |
| Siinqee | siinqee_html | 6 | ✅ |
| Global | global_html | 4 | ✅ |
| Ahadu | ahadu_html | 2 | ✅ |
| CBO | cbo_html | 28 | Cooperative Bank of Oromia |
| Tsehay | tsehay_html | 13 | Last effective date: Oct 19 |
| Sidama | sidama_html | 12 | Last effective date: Oct 19 |

**Oromia and Anbesa**: Use `oromia_af` and `anbesa_af` adapter keys - these are intentionally using AddisFortuneAdapter as primary (not fallback).

### ✅ AF-ONLY Banks (Correctly Using AddisFortuneAdapter as Primary)

These banks DON'T have dedicated adapters, so they should use AddisFortuneAdapter:

| Bank | Adapter Key | Oct 21 Records | Notes |
|------|-------------|----------------|-------|
| NBE | nbe_af | 76 | National Bank of Ethiopia |
| Addis Bank | addis_bank_af | 6 | Last effective date: Oct 20 |
| Hijra | hijra_af | 10 | Last effective date: Oct 19 |

---

## Impact Summary

### Before Fix (All Day Today Until 10:08 AM)
- **30+ banks** with dedicated adapters were incorrectly using AddisFortuneAdapter
- Most returned **0 records** because AF adapter expects Livewire JSON, not HTML
- Only 3 banks with `*_af` keys worked correctly
- System collected data from only ~10 banks

### After Fix (10:13 AM Collection)
- All 30+ banks now use their **dedicated adapters**
- **Massive improvement**: 34 banks succeeded, many with new Oct 21 data
- Total new records accepted: **~300+ records** in one collection run
- Only AF-only banks (NBE, Addis Bank, Hijra) use AddisFortuneAdapter

---

## The Fix

Changed `_load_adapter()` to only check AF for AF-only keys:

```python
def _load_adapter(adapter_key: str):
    from adapters.addis_fortune.adapter import get_adapter_for_key, AF_SLUG_MAP
    # ONLY use AF adapter for keys that are ONLY in AF (no dedicated adapter)
    # These are: addis_bank_af, hijra_af, nbe_af
    af_only_keys = {"addis_bank_af", "hijra_af", "nbe_af"}
    if adapter_key in af_only_keys:
        af = get_adapter_for_key(adapter_key)
        if af is not None:
            return af
    
    # Continue with normal adapter loading logic...
```

---

## Additional Issue: NIB HTML Structure Change

NIB required an additional fix because their website HTML structure changed:
- **Removed**: Country column from table
- **OLD**: 6 columns `[Country, Currency, cash_buy, cash_sell, txn_buy, txn_sell]`
- **NEW**: 5 columns `[Currency, cash_buy, cash_sell, txn_buy, txn_sell]`
- **Fix**: Updated `adapters/nib/adapter.py` column indices

---

## Verification

Run this query to see current status:

```sql
SELECT 
    b.code,
    rs.adapter_key,
    COUNT(CASE WHEN DATE(ro.fetched_at) = '2026-10-21' THEN 1 END) as oct21_records,
    MAX(ro.effective_date) as last_effective_date
FROM bank b
JOIN rate_source rs ON rs.bank_id = b.id
LEFT JOIN rate_observation ro ON ro.source_id = rs.id
WHERE rs.is_enabled = true
GROUP BY b.code, rs.adapter_key
ORDER BY oct21_records DESC;
```

---

## Lessons Learned

1. **Fallback systems should be explicit**: Don't use presence in a map to determine fallback behavior
2. **Test adapter loading separately**: The adapter loading logic should be tested independently
3. **Monitor adapter types**: Log which adapter class is actually being used for each bank
4. **Schema fingerprinting is critical**: The duplicate `_check_schema()` function masked this issue for weeks

---

## Files Modified

1. `scheduler/runner.py` - Fixed `_load_adapter()` to only use AF for AF-only keys
2. `adapters/nib/adapter.py` - Fixed column mappings for new HTML structure
3. `scheduler/runner.py` - Removed duplicate `_check_schema()` function (separate bug)
