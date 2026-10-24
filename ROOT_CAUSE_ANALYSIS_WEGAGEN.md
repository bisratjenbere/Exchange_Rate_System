# Root Cause Analysis: Wegagen Rates Not Showing in UI

**Date**: October 21, 2026  
**Issue**: User reports "wegagen has today exchange rate posted but our system show no rate"

## Executive Summary

The Oct 21, 2026 Wegagen data **IS** being collected and stored correctly in the database with `is_current=TRUE`. However, it's **not visible in the UI** because:

1. The Wegagen adapter marks all records as `category="UNKNOWN"` 
2. The trusted view query filters out records with `category_id IS NULL`
3. Therefore, ALL Wegagen data is excluded from the UI

**This is NOT a fingerprint bug or deduplication bug** - it's a business logic conflict about how to handle category ambiguity.

---

## Investigation Timeline

### Step 1: Verified Live API Data
Wegagen's live API **currently shows Oct 21 data**:
```
USD Date=2026-10-21 Buy=162.1739 Sell=165.4174
```

### Step 2: Checked Database
Found Oct 21 data **IS in the database**:
```
ID 4156: Oct 21, 162.1739, is_current=TRUE, category_id=NULL
```

### Step 3: Checked Trusted View Query
Line 403 in `trusted_view/query.py` has a LOCKED rule:
```python
"o.category_id IS NOT NULL",  # Filters out UNKNOWN category
```

### Step 4: Checked Wegagen Adapter
Line 107 in `adapters/wegagen/adapter.py`:
```python
category="UNKNOWN",  # HARD-CODED - category ambiguity
```

**Comment in code**:
> "buying == tra_buying for all observed records — category ambiguity (TO VERIFY)"

---

## Technical Details

### Data Flow

```
Wegagen API (Oct 21 data)
    ↓
Wegagen Adapter → category="UNKNOWN"
    ↓
Ingest Pipeline → category_id = NULL (UNKNOWN not in rate_category table)
    ↓
Database → Stored with is_current=TRUE but category_id=NULL
    ↓
Trusted View Query → Filtered out by "category_id IS NOT NULL"
    ↓
UI → No Wegagen data visible
```

### Why Category is UNKNOWN

From `adapters/wegagen/adapter.py` docstring:
```
buying == tra_buying for all observed records — category ambiguity (TO VERIFY).
Emit one AdapterRecord per row with category UNKNOWN until category is confirmed.
```

The Wegagen API returns:
- `buying` and `selling` (cash rates)
- `tra_buying` and `tra_selling` (transaction rates)

In observed data, `buying == tra_buying`, making it unclear which category to use.

### Affected Records

**All Wegagen records** have `category_id = NULL`:
```sql
SELECT COUNT(*) FROM rate_observation o
JOIN rate_source rs ON rs.id = o.source_id  
JOIN bank b ON b.id = rs.bank_id
WHERE b.code = 'WEGAGEN' AND o.category_id IS NULL;
-- Returns: ALL records
```

---

## Impact Analysis

### What's Working ✅
- HTTP fetching from Wegagen API
- JSON parsing
- Fingerprint computation (includes collection_date correctly)
- Deduplication logic
- Data storage in database
- `is_current` flag management

### What's NOT Working ❌
- Wegagen data visibility in UI
- Wegagen data in trusted view queries
- Any API endpoint using trusted view

### Other Banks Affected

Need to verify if other adapters also use `category="UNKNOWN"`:
```bash
grep -r 'category="UNKNOWN"' adapters/*/adapter.py
```

---

## Root Cause

**This is a design conflict**, not a bug:

1. **Design Intent**: The system was designed to exclude UNKNOWN category data from the trusted view to ensure data quality. This is a LOCKED rule enforced at the query layer.

2. **Implementation Reality**: The Wegagen adapter was implemented to emit UNKNOWN category because of genuine category ambiguity in the source data.

3. **Conflict**: These two decisions are incompatible - if ALL data from a bank is UNKNOWN category, that bank will be invisible in the UI.

---

## Solutions

### Option 1: Accept Default Category (RECOMMENDED)
**Change**: Modify Wegagen adapter to use a default category (e.g., "transactional")

**Pros**:
- Quickest fix
- Makes data immediately visible
- No schema changes
- Aligns with user expectation: "show what banks publish"

**Cons**:
- Might be incorrect category (needs verification)
- Other adapters may have same issue

**Implementation**:
```python
# In adapters/wegagen/adapter.py line 107
category="transactional",  # Default until verified
```

---

### Option 2: Show UNKNOWN with Warning
**Change**: Modify trusted view query to include UNKNOWN category with visible warning

**Pros**:
- Preserves data quality intent
- Makes ambiguity visible to users
- No adapter changes needed

**Cons**:
- Requires query layer changes
- Breaks "LOCKED rules" principle
- May affect other banks with UNKNOWN data

**Implementation**:
```python
# In trusted_view/query.py
# Remove "o.category_id IS NOT NULL" from locked_rules
# Add computed field "has_unknown_category" for UI warning
```

---

### Option 3: Category Resolution Workflow
**Change**: Create workflow to manually classify UNKNOWN records

**Pros**:
- Ensures correct categorization
- Proper data quality process
- Scalable to other banks

**Cons**:
- Most complex solution
- Requires UI development
- Delayed data visibility

**Implementation**:
- Add `category_resolution` table
- Create admin UI for classification
- Background job to reclassify records

---

### Option 4: Dual-Category Emission
**Change**: Wegagen adapter emits TWO records per row (cash + transactional)

**Pros**:
- Covers both possible categories
- No data loss
- Immediate visibility

**Cons**:
- Duplicates data
- May not match bank's intent
- Confusing for users

---

## Recommended Action Plan

**Phase 1: Immediate Fix** (Today)
1. Change Wegagen adapter `category="UNKNOWN"` → `category="transactional"`
2. Re-collect Wegagen data
3. Verify Oct 21 data now visible in UI

**Phase 2: Verification** (This week)
1. Contact Wegagen to clarify: are rates cash or transactional?
2. Verify `buying == tra_buying` across all historical data
3. Update adapter if category confirmed

**Phase 3: System-Wide** (Next sprint)
1. Audit all adapters for `category="UNKNOWN"`
2. Document category resolution process in ADR
3. Consider Option 2 (show UNKNOWN with warning) for future edge cases

---

## Files Involved

- `adapters/wegagen/adapter.py` - Sets category="UNKNOWN"
- `pipeline/ingest.py` - Maps category to category_id
- `trusted_view/query.py` - Filters out NULL category_id
- `api/app.py` - Uses trusted view queries
- `db/migrations/001_initial_schema.sql` - rate_category table definition

---

## Questions for Discussion

1. **Business**: Should we show rates with uncertain categories, or wait for verification?
2. **Technical**: Should category filtering be at query layer or application layer?
3. **Data Quality**: What's our tolerance for "probably transactional but not confirmed"?

---

## Appendix: Database Evidence

### Current Wegagen USD Records
```
ID    EffDate      Buy           Current  Category
1877  2026-10-16   161.7253      False    UNKNOWN (NULL)
2021  2026-10-17   161.7253      False    UNKNOWN (NULL)
2669  2026-10-19   161.7253      False    UNKNOWN (NULL)
3969  2026-10-20   161.7253      False    UNKNOWN (NULL)
4156  2026-10-21   162.1739      TRUE     UNKNOWN (NULL)  ← Today's data!
```

### Rate Category Table
```
Code                    ID    Active
cash                    1     TRUE
transactional           2     TRUE
weighted_average        3     TRUE
indicative_reference    4     TRUE
```

### Wegagen Source Config
```
default_category: transactional
```

**Note**: The source has `default_category='transactional'` configured in the database, but the adapter overrides it by explicitly setting `category="UNKNOWN"` in the AdapterRecord.
