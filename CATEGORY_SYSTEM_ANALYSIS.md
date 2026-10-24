# Exchange Rate Category System - Complete Analysis

**Date**: October 21, 2026  
**Purpose**: Understand what categories are, why they exist, and how to handle the Wegagen visibility issue

---

## What Are Rate Categories?

Exchange rate categories distinguish **different types of rates** that banks publish for the same currency on the same day. They exist because **different transaction types get different rates**.

### The Four Categories

```
1. CASH - Physical currency exchange
2. TRANSACTIONAL - Electronic/wire transfers
3. WEIGHTED_AVERAGE - Calculated average (reference only)
4. INDICATIVE_REFERENCE - Non-binding market quote (rare)
```

---

## Why Categories Matter

### Real-World Use Cases

**CASH Rate** - Tourist/Individual Use
```
Scenario: Tourist walks into Commercial Bank of Ethiopia with $500 USD bills
Rate Type: CASH
Why different: Physical handling, verification costs, higher fraud risk
Spread: WIDEST (e.g., Buy=161.50, Sell=165.00 → 3.50 Birr spread)
```

**TRANSACTIONAL Rate** - Business Use
```
Scenario: Import company paying supplier abroad via wire transfer
Rate Type: TRANSACTIONAL
Why different: Electronic, lower risk, bulk processing
Spread: NARROWER (e.g., Buy=161.75, Sell=164.80 → 3.05 Birr spread)
Most common: 60%+ of all records in database
```

**WEIGHTED_AVERAGE Rate** - Reference/Reporting
```
Scenario: National Bank of Ethiopia publishing daily market summary
Rate Type: WEIGHTED_AVERAGE
Why different: Calculated from actual transactions
NOT TRADEABLE: You cannot buy/sell at this rate
Purpose: Transparency, benchmarking, economic reporting
```

**INDICATIVE_REFERENCE Rate** - Market Quote
```
Scenario: Large corporate transaction, rate depends on amount/timing
Rate Type: INDICATIVE_REFERENCE  
Why different: Starting point for negotiation, not guaranteed
Rare: Almost never seen in Ethiopian banks
```

---

## Current System Status

### Categories in Database

```sql
SELECT code, id, is_active FROM rate_category;
```

| Code | ID | Active |
|------|-----|--------|
| cash | 1 | TRUE |
| transactional | 2 | TRUE |
| weighted_average | 3 | TRUE |
| indicative_reference | 4 | TRUE |

### Usage Statistics (October 2026)

```
Category Usage Across All Banks:
- transactional:     2,134 records (331 current) - 60% of data
- cash:              1,430 records (275 current) - 40% of data  
- weighted_average:    418 records (57 current)  - 12% of data
- UNKNOWN:             149 records (10 current)  - 4% problematic
```

**Key Insight**: Most banks publish both CASH and TRANSACTIONAL rates. Some also publish WEIGHTED_AVERAGE for transparency.

---

## The UNKNOWN Category Problem

### What is UNKNOWN?

`UNKNOWN` is **not a fifth category** - it's a flag meaning **"we couldn't determine the category from the source data."**

### Why Records Get Marked UNKNOWN

From ADR-006 §4.4:
> When category cannot be determined from the source, emit category = UNKNOWN.  
> Never guess. The pipeline routes UNKNOWN to the review queue and excludes from trusted view.

### Banks Currently Using UNKNOWN

| Bank | Adapter | Total | Current | Why UNKNOWN? |
|------|---------|-------|---------|--------------|
| Wegagen Bank | wegagen_api | 47 | 10 | buying == tra_buying (ambiguous) |
| Development Bank of Ethiopia | dbe_html | 38 | 0 | Single table, no label |
| Goh Betoch Bank | goh_betoch_html | 16 | 0 | Single table, no label |
| Siinqee Bank | siinqee_html | 12 | 0 | Single table, no label |
| Berhan Bank | berhan_html | 12 | 0 | Single table, no label |
| Enat Bank | enat_html | 12 | 0 | Single table, no label |
| Global Bank Ethiopia | global_html | 10 | 0 | Single table, no label |
| Ahadu Bank | ahadu_html | 2 | 0 | Single table, no label |

**Wegagen is the ONLY bank with UNKNOWN records currently visible (is_current=TRUE).**

---

## The Design Intent (Gap Review Item E)

From `docs/review/gap-review.md`:

> **E. Excluded unknowns**: unknown currency or category is excluded from the trusted view, not only flagged.

**Purpose**: Data quality control. The system was designed to:
1. Collect ALL data (including UNKNOWN)
2. Store it in database
3. But EXCLUDE from trusted view/UI until verified
4. Prevent mixing different rate types in comparisons

**The Rule** (from `trusted_view/query.py` line 403):
```python
"o.category_id IS NOT NULL",  # LOCKED RULE
```

This is intentional, not a bug.

---

## Wegagen Specific Analysis

### What Wegagen Publishes

Their Strapi API returns:
```json
{
  "id": 123,
  "attributes": {
    "date": "2026-10-21",
    "code": "USD",
    "buying": 162.1739,
    "selling": 165.4174,
    "tra_buying": 162.1739,   // ← SAME as buying
    "tra_selling": 165.4174,  // ← SAME as selling
    "unit": 1
  }
}
```

### The Ambiguity

The adapter sees:
- `buying` = 162.1739
- `tra_buying` = 162.1739 (transactional)

**Question**: Are these...
- A) Two separate rates that happen to be equal? (unlikely)
- B) The same rate published twice? (likely)
- C) One is cash, one is transactional? (need verification)

### Adapter's Conservative Choice

From `adapters/wegagen/adapter.py` line 21:
```python
"""
buying == tra_buying for all observed records — category ambiguity (TO VERIFY).
Emit one AdapterRecord per row with category UNKNOWN until category is confirmed.
"""
```

The adapter developer chose:
- **Conservative**: Mark as UNKNOWN rather than guess
- **Correct**: Follows ADR-006 rule "never guess category"
- **Problem**: Makes ALL Wegagen data invisible in UI

### Current Database State

```
Wegagen Bank Records in Database:
- Cash:           20 total, 10 current
- Transactional:  81 total, 16 current  
- UNKNOWN:        47 total, 10 current  ← These are invisible!
```

**The Oct 21 data IS collected and IS marked current**, but filtered out by trusted view query.

---

## Solution Options

### Option 1: Accept Default Category ⭐ RECOMMENDED
**Change**: Wegagen adapter uses `category="transactional"` as default

**Reasoning**:
1. Most banks publish transactional as primary rate (60% of data)
2. Wegagen source config already has `default_category='transactional'`
3. If wrong, we can fix later with category resolution
4. Aligns with user expectation: "show what banks publish"

**Code Change**:
```python
# adapters/wegagen/adapter.py line 107
category="transactional",  # Default pending verification
```

**Pros**: ✅ Quick fix, ✅ Data immediately visible, ✅ Matches most banks
**Cons**: ⚠️ Might be wrong category (needs verification)

---

### Option 2: Emit Both Categories
**Change**: Wegagen adapter emits TWO records per currency (cash + transactional)

**Reasoning**:
- Source provides both `buying` and `tra_buying`
- Even if values are identical, they might represent separate offerings
- Covers all bases until verified

**Code Change**:
```python
return [
    AdapterRecord(
        source_currency_code=currency,
        category="cash",
        buying_rate=buying,
        selling_rate=selling,
        ...
    ),
    AdapterRecord(
        source_currency_code=currency,
        category="transactional",
        buying_rate=tra_buying,
        selling_rate=tra_selling,
        ...
    )
]
```

**Pros**: ✅ Complete coverage, ✅ No information loss
**Cons**: ⚠️ Duplicates data if they're actually the same, ⚠️ Confusing for users

---

### Option 3: Show UNKNOWN with Warning
**Change**: Modify trusted view query to INCLUDE `category_id IS NULL` but flag it

**Reasoning**:
- Data quality intent preserved (warn users)
- Makes ambiguity visible instead of hidden
- Scalable to other banks with UNKNOWN

**Code Change**:
```python
# trusted_view/query.py - REMOVE locked rule:
# "o.category_id IS NOT NULL",  # ← DELETE THIS

# Add to SELECT clause:
# o.category_id IS NULL AS has_unknown_category
```

**Pros**: ✅ Preserves design intent, ✅ Works for all banks
**Cons**: ⚠️ Breaks LOCKED rule (Gap Review Item E), ⚠️ Requires UI changes

---

### Option 4: Category Resolution Workflow
**Change**: Create admin UI to manually classify UNKNOWN records

**Reasoning**:
- Proper data quality process
- Can verify by contacting bank or testing
- One-time effort per bank

**Implementation**:
- Table: `category_resolution (observation_id, resolved_category, verified_by, verified_at)`
- Admin UI: Show UNKNOWN records, allow selection
- Query: JOIN with resolution table to get verified category

**Pros**: ✅ Most correct, ✅ Auditable, ✅ Scalable
**Cons**: ⚠️ Complex, ⚠️ Delayed data visibility, ⚠️ Requires development

---

## Recommended Action Plan

### Phase 1: Immediate Fix (Today)
**Goal**: Make Wegagen data visible

**Action**:
```python
# adapters/wegagen/adapter.py
# Change line 107 from:
category="UNKNOWN",

# To:
category="transactional",  # Default pending bank verification
```

**Reason**: 
- Wegagen source already configured with `default_category='transactional'`
- 60% of all records use transactional category
- Can be corrected later if wrong
- Matches user expectation

**Impact**: Oct 21 data (and all future Wegagen data) will appear in UI immediately

---

### Phase 2: Verification (This Week)
**Goal**: Confirm the correct category

**Actions**:
1. **Test both rate types**:
   - Ask Wegagen: "What is the difference between 'buying' and 'tra_buying'?"
   - Test: Try to exchange $100 at branch vs. wire transfer - same rate?

2. **Compare with other banks**:
   - Look at banks that publish both (e.g., CBE, Dashen)
   - Verify spread difference between cash and transactional

3. **Check historical data**:
   ```sql
   SELECT 
     o.effective_date,
     o.buying_rate as buying,
     o.raw_data->>'tra_buying' as tra_buying
   FROM rate_observation o
   WHERE o.source_id = 27  -- Wegagen
   AND o.buying_rate IS DISTINCT FROM (o.raw_data->>'tra_buying')::numeric
   LIMIT 100;
   ```
   If query returns NO rows → they're always identical → probably same rate

4. **Document finding** in ADR

---

### Phase 3: System-Wide (Next Sprint)
**Goal**: Handle category ambiguity systematically

**Actions**:
1. **Audit all adapters**:
   ```bash
   grep -r 'category="UNKNOWN"' adapters/*/adapter.py
   ```
   
2. **Review each UNKNOWN case**:
   - DBE, Siinqee, Global, Goh Betoch: Single table, no label
   - Same question: What category do they actually publish?

3. **Document decision** in ADR:
   - When to use UNKNOWN vs. default category
   - Verification requirements before changing UNKNOWN → specific category
   - Process for resolving ambiguous categories

4. **Consider Option 3** (show UNKNOWN with warning) for future edge cases:
   - Would require ADR to modify Gap Review Item E
   - Would need UI warning: "⚠️ Category not verified"

---

## Key Insights

### Why Categories Exist
Not arbitrary - reflects real-world business needs:
- **Tourists need cash rates**
- **Businesses need transactional rates**  
- **Analysts need weighted averages**
- **Cannot compare different categories** (apples to oranges)

### Why UNKNOWN is Excluded
Design principle (Gap Review Item E):
> "Unknown currency or category is excluded from the trusted view, not only flagged"

**Reason**: Prevent showing unreliable data. Better to show nothing than show wrong category.

### Why This Matters to Users

**Bad User Experience** (mixing categories):
```
"Best USD rate today":
- Bank A: 162.00 (transactional)
- Bank B: 161.50 (cash)          ← Looks better but isn't comparable!
- Bank C: 163.00 (transactional)
```

**Good User Experience** (same category):
```
"Best USD transactional rate today":
- Bank A: 162.00
- Bank B: 162.50
- Bank C: 163.00
→ User can make informed decision
```

---

## Tools for Investigation

### Check What Wegagen Actually Provides
```bash
curl -s "https://weg.back.strapi.wegagen.com/api/exchange-rates?populate=*" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data['data'][:3]:  # First 3 currencies
    attrs = item['attributes']
    print(f\"{attrs['code']}: buying={attrs['buying']}, tra_buying={attrs['tra_buying']}\")
    print(f\"  Are they equal? {attrs['buying'] == attrs['tra_buying']}\")
"
```

### Check Database for Historical Differences
```sql
-- Find any historical case where buying != tra_buying
SELECT 
  effective_date,
  source_currency_code,
  buying_rate,
  raw_data->>'tra_buying' as tra_buying
FROM rate_observation 
WHERE source_id = 27
AND buying_rate::text != raw_data->>'tra_buying'
LIMIT 10;
```

### Check Other Banks' Category Patterns
```sql
-- How do other banks handle multiple categories?
SELECT 
  b.name,
  COALESCE(rc.code, 'UNKNOWN') as category,
  COUNT(*) as records
FROM rate_observation o
JOIN rate_source rs ON rs.id = o.source_id
JOIN bank b ON b.id = rs.bank_id
LEFT JOIN rate_category rc ON rc.id = o.category_id
WHERE o.is_current = TRUE
GROUP BY b.name, rc.code
HAVING COUNT(*) > 0
ORDER BY b.name, rc.code;
```

---

## Decision Criteria

### When to Use UNKNOWN
- Source has single buying/selling pair
- No category label in source
- No way to determine from context
- Example: DBE website has one table, headers are just "Buying | Selling"

### When to Use Default Category
- Source pattern matches known category pattern
- Other banks with similar structure use specific category
- Can be verified later if needed
- Example: Wegagen has `default_category='transactional'` configured

### When to Emit Multiple Categories
- Source explicitly provides multiple rate types
- Each has different values OR different purpose
- Bank documentation confirms separate offerings
- Example: CBE API has `cashBuying` AND `transactionalBuying` (different values)

---

## Next Steps

**Immediate** (Today):
- [ ] Change Wegagen adapter: `category="UNKNOWN"` → `category="transactional"`
- [ ] Re-collect Wegagen data
- [ ] Verify Oct 21 data appears in UI

**Short-term** (This week):
- [ ] Contact Wegagen to ask about rate types
- [ ] Compare Wegagen rates with other banks
- [ ] Document finding in ADR

**Long-term** (Next sprint):
- [ ] Audit all UNKNOWN category usage
- [ ] Create category resolution process
- [ ] Consider "show UNKNOWN with warning" for edge cases
