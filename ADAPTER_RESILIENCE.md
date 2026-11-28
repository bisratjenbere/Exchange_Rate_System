# Adapter Resilience Strategy: Senior-Level Techniques

## Current Situation

**3 Banks Need Updates Right Now:**
1. **Bank of Abyssinia** (`boa.py`) - https://www.bankofabyssinia.com/exchange-rates/
2. **Hibret Bank** (`hibret.py`) - https://hibretbank.com.et/exchange-rate/
3. **Amhara Bank** (`amhara.py`) - https://amarabanksc.com/

All three use `HtmlTableAdapter` with `TableSpec` pattern.

---

## Why HTML Changes Break Adapters

Banks change their websites when they:
- Redesign their site (new CSS framework, layout)
- Change table structure (add/remove columns, reorder)
- Move to JavaScript rendering (React, Vue)
- Add authentication/CAPTCHA
- Change URLs or endpoints

**Question:** "Do we always need to update adapters when banks change HTML?"

**Answer:** No! With proper **resilient design patterns**, we can minimize breakage.

---

## Senior-Level Resilience Techniques

### ✅ **Already Implemented in Your System**

#### 1. **Header-Based Column Matching (Not Positional)**
```python
# BRITTLE (position-based):
currency = cells[0]  # Breaks if column order changes
buying = cells[1]
selling = cells[2]

# RESILIENT (header-based) - ALREADY IN YOUR CODE:
headers = {
    "currency": ("currency", "code", "symbol"),  # Multiple variants
    "buy": ("buying", "cash buying", "we buy"),
    "sell": ("selling", "cash selling", "we sell"),
}
```
✅ **Benefit:** Works even if columns are reordered or renamed slightly.

#### 2. **Multiple Header Variants**
```python
"buy": ("buying", "cash buying", "we buy", "buying rate")
```
✅ **Benefit:** Tolerates different wording/translations.

#### 3. **Fuzzy Text Matching**
```python
# In html_table.py line 73:
if any(variant.lower() in cell_text for variant in variants):
```
✅ **Benefit:** "Buying Rate" matches "buying", "Cash Buying" matches "buying".

#### 4. **Multiple Table Support**
```python
for table in soup.find_all("table"):
    # Try each table until one matches
```
✅ **Benefit:** Works if rate table is 2nd or 3rd table on page.

#### 5. **Fallback Mechanism**
```python
# infrastructure/fallback_policy.py
# If primary source fails → try Addis Fortune data
```
✅ **Benefit:** System keeps working even if one bank breaks.

---

### 🔧 **Additional Techniques to Add**

#### 6. **CSS Selector Alternatives**
```python
@dataclass(frozen=True)
class TableSpec:
    # ... existing fields ...
    table_selectors: tuple[str, ...] = (
        "table.exchange-rates",
        "table#rates",
        "table",  # Fallback to any table
    )
```

**Usage:**
```python
for selector in spec.table_selectors:
    table = soup.select_one(selector)
    if table and matches_headers(table):
        return table
```

#### 7. **Schema Versioning & Auto-Detection**
```python
class TableSpec:
    schema_version: int = 1
    schema_fingerprint: str = ""  # Hash of table structure
    
    def detect_schema_change(self, html: str) -> bool:
        """Detect if table structure changed."""
        current_fp = self._compute_fingerprint(html)
        return current_fp != self.schema_fingerprint
```

**Benefit:** Alert you when structure changes, before data collection fails.

#### 8. **Flexible Cell Extraction**
```python
def extract_cell_value(cell) -> str:
    """Extract text from cell, handling complex HTML."""
    # Try multiple strategies:
    # 1. Direct text
    text = cell.get_text(strip=True)
    if text:
        return text
    
    # 2. Data attributes
    if cell.get('data-value'):
        return cell['data-value']
    
    # 3. Nested spans/divs
    for tag in ['span', 'div', 'strong']:
        elem = cell.find(tag)
        if elem:
            return elem.get_text(strip=True)
    
    return ""
```

#### 9. **Graceful Degradation**
```python
class TableSpec:
    optional_columns: tuple[str, ...] = ("effective_date", "last_updated")
    
    def parse(self, html: str) -> ParseOutcome:
        # Required columns must exist
        if not all(col in column_map for col in self.required):
            return ParseOutcome.failed(...)
        
        # Optional columns are nice-to-have
        for opt_col in self.optional_columns:
            if opt_col not in column_map:
                issues.append(RowIssue(
                    "header", IssueCode.MISSING_COLUMN,
                    f"Optional column '{opt_col}' not found",
                    Severity.WARNING
                ))
```

#### 10. **API-First with HTML Fallback**
```python
class BankAdapter:
    def fetch_rates(self):
        # Try API first (more stable)
        try:
            return self.fetch_api()
        except:
            # Fallback to HTML scraping
            return self.fetch_html()
```

---

## Recommended Implementation Plan

### Phase 1: Quick Wins (1-2 hours)

**Add more header variants to the 3 broken banks:**

```python
# adapters/banks/boa.py
SPEC = TableSpec(
    key="boa_html",
    url="https://www.bankofabyssinia.com/exchange-rates/",
    headers={
        "currency": ("currency", "code", "symbol", "currency code", "curr"),
        "buy": ("buying", "cash buying", "we buy", "buying rate", "buy rate", "purchase"),
        "sell": ("selling", "cash selling", "we sell", "selling rate", "sell rate"),
    },
    required=("currency", "buy", "sell"),
    # NEW: Try multiple table selectors
    table_selectors=(
        "table.exchange-rates",
        "table.forex",
        "table#rates",
        "div.rates-table table",
        "table",  # Fallback
    ),
)
```

### Phase 2: Infrastructure Improvements (4-6 hours)

1. **Add `table_selectors` to TableSpec**
   - Edit: `adapters/core/html_table.py`
   - Add: Multiple CSS selector fallbacks

2. **Add schema change detection**
   - Alert when table structure changes
   - Log fingerprint mismatches
   - Auto-notify developers

3. **Add "last known good" snapshot**
   - Store working HTML examples in `test_data/`
   - Use for regression testing
   - Quick comparison when site breaks

### Phase 3: Monitoring & Alerting (2-3 hours)

1. **Add adapter health dashboard**
   ```python
   # Show:
   # - Which adapters succeeded/failed
   # - Structure change detection
   # - Success rate trends
   ```

2. **Alert on consecutive failures**
   ```python
   if bank.consecutive_failures >= 3:
       send_alert(f"{bank.name} needs attention")
   ```

---

## Best Practices Going Forward

### DO ✅

1. **Use header-based matching** (already doing this)
2. **Add multiple header variants** when creating new adapters
3. **Test adapters with real HTML** from bank websites
4. **Keep fallback mechanism** (Addis Fortune)
5. **Monitor adapter success rates** in GitHub Actions
6. **Version control test HTML** in repo

### DON'T ❌

1. **Don't use positional indexing** (`cells[0]`, `cells[1]`)
2. **Don't hardcode CSS classes** that might change
3. **Don't assume column order** stays the same
4. **Don't ignore warnings** about structure changes
5. **Don't skip testing** after bank site updates

---

## Real-World Example

### Brittle Adapter (Bad):
```python
# Breaks if:
# - Columns reorder
# - Class name changes
# - Table ID changes
table = soup.select_one("#exchange_rates_table")
rows = table.find_all("tr")
for row in rows[1:]:  # Skip header
    cells = row.find_all("td")
    currency = cells[0].text  # Position 0
    buying = cells[1].text    # Position 1
    selling = cells[2].text   # Position 2
```

### Resilient Adapter (Good):
```python
# Works even if:
# - Columns reorder
# - Headers renamed slightly
# - Multiple tables on page
spec = TableSpec(
    headers={
        "currency": ("currency", "curr", "code"),
        "buy": ("buying", "buy", "purchase"),
        "sell": ("selling", "sell"),
    }
)
# Auto-finds correct columns by header text
adapter = HtmlTableAdapter(spec)
```

---

## Conclusion

**Question:** "Do we always need to update adapters when HTML changes?"

**Answer:** 
- With **brittle adapters** → Yes, every small change breaks it
- With **resilient adapters** → Only major redesigns need updates
- With **fallback mechanism** → System keeps working even if one breaks

**Your Current System:**
- ✅ Already uses resilient patterns (header-based matching)
- ✅ Has fallback mechanism (Addis Fortune)
- 🔧 Could add: More header variants, CSS selector fallbacks
- 🔧 Could add: Schema change detection, alerting

**Expected Improvement:**
- Current: ~20-30% of adapters break per year
- With improvements: ~5-10% of adapters break per year
- With API-first: ~1-2% of adapters break per year

**Next Step:** Fix the 3 broken banks by visiting their sites and updating header variants.
