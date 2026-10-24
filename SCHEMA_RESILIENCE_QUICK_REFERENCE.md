# 🔧 Schema Change Resilience - Quick Reference Guide

**For Developers**: How to use the new resilience features

---

## 📋 Overview

The system now automatically handles common schema changes through:
1. **Multi-strategy table detection** - Tries multiple approaches to find tables
2. **Fuzzy CSS selectors** - Handles class name changes
3. **Enhanced field patterns** - Recognizes field name variations

**No code changes required** - existing adapters automatically benefit!

---

## 🚀 For Adapter Developers

### Creating a New HTML Table Adapter

```python
from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from bs4 import BeautifulSoup

class NewBankAdapter(FieldStructureMixin, HTMLTableAdapter):
    """New bank adapter with automatic resilience."""
    
    # Empty config = auto-detect everything
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        return "https://newbank.com/rates"
    
    def get_adapter_key(self) -> str:
        return "newbank_html"
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        result = ParseResult()
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:  # Skip header
                cells = [c.get_text(strip=True) for c in row.find_all("td")]
                if len(cells) < 3:
                    continue
                
                # Create dict with any field names you extract
                row_dict = {
                    "buying": cells[1],
                    "selling": cells[2],
                }
                
                # Field detection handles the rest!
                detected_records = self.detect_and_emit(
                    data=row_dict,
                    currency=cells[0],
                    effective_date=None,
                    effective_date_basis="collection_date_fallback"
                )
                
                result.records.extend(detected_records)
        
        return result
```

**That's it!** The adapter automatically:
- ✅ Tries multiple strategies to find tables
- ✅ Handles CSS class changes
- ✅ Detects field name variations
- ✅ Logs when non-standard strategies used

---

## 🔍 Supported Field Name Variations

The system now recognizes these patterns automatically:

### Original Patterns (Still Supported)
- `buying`, `selling`
- `cashBuying`, `cashSelling`
- `cash_buying`, `cash_selling`
- `tra_buying`, `tra_selling`

### NEW: Numbered Variants
- `buying_1`, `selling_1`
- `buying_2`, `selling_2`
- `cash_buying_1`, `cash_selling_1`

### NEW: Hyphenated Forms
- `cash-buying`, `cash-selling`
- `buying-rate`, `selling-rate`

### NEW: Abbreviated Forms
- `buy_r`, `sell_r`
- `buy_rt`, `sell_rt`
- `buyRate`, `sellRate`

### NEW: Spacing Variations
- `buying rate`, `selling rate`
- `cash buying rate`, `cash selling rate`

**Add your own patterns** by updating `field_detection/detector.py`

---

## 🛠️ Debugging Schema Changes

### When a Bank's Website Changes

**Step 1: Check the logs**
```bash
grep "Found tables using" logs/collection.log
```

**What you'll see**:
```
INFO [2026-10-23 08:30:15] bank_key: Found tables using 'fuzzy_class' strategy
```

**Meaning**:
- `exact` = Normal operation (no CSS change)
- `fuzzy_class` = CSS class was renamed, but system recovered
- `div_fallback` = Table → div migration detected
- No message = Exact strategy worked

**Step 2: Investigate further** (if fuzzy/div used)
```python
from adapters.bank_name.adapter import BankAdapter
adapter = BankAdapter()

# Test with latest HTML
html = fetch_from_url(adapter.get_source_url())
soup = BeautifulSoup(html, "html.parser")

# See which strategy works
tables, strategy = adapter._find_tables_resilient(soup)
print(f"Strategy: {strategy}")
print(f"Tables found: {len(tables)}")
```

**Step 3: Update fixture** (if needed)
```bash
# Save new HTML structure for testing
cp fixtures/bank_name/normal.html fixtures/bank_name/normal_old.html
curl https://bank.com/rates > fixtures/bank_name/normal.html
```

---

## 🧪 Testing Your Adapter

### Run Resilience Tests

```bash
# Test Phase 1 enhancements
python3 test_phase1_resilience.py

# Test your specific adapter
python3 -m pytest tests/test_your_adapter.py -v
```

### Test Against Variations

```python
# Test with different HTML structures
test_cases = [
    # Original
    '<table class="rates"><tr><td>USD</td></tr></table>',
    
    # CSS class renamed
    '<table class="exchange-rates-2024"><tr><td>USD</td></tr></table>',
    
    # No class
    '<table><tr><td>USD</td></tr></table>',
]

for html in test_cases:
    result = adapter.parse(html)
    assert result.is_success()
```

---

## 📊 Monitoring Your Adapter

### Check Strategy Usage

```sql
-- Query to see which strategies are being used
SELECT 
    adapter_key,
    COUNT(*) as total_runs,
    SUM(CASE WHEN notes LIKE '%fuzzy_class%' THEN 1 ELSE 0 END) as fuzzy_used,
    SUM(CASE WHEN notes LIKE '%div_fallback%' THEN 1 ELSE 0 END) as div_used
FROM collection_run
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY adapter_key
HAVING fuzzy_used > 0 OR div_used > 0;
```

### Add Custom Logging

```python
def _process_tables(self, soup, tables, **kwargs):
    import logging
    logger = logging.getLogger(__name__)
    
    # Log when something unusual happens
    if len(tables) != 2:  # Expected 2 tables
        logger.warning(f"{self.get_adapter_key()}: Expected 2 tables, found {len(tables)}")
    
    # Continue normal processing
    result = ParseResult()
    # ...
    return result
```

---

## 🔧 Configuration Options

### Customize Field Detection

```python
class CustomAdapter(FieldStructureMixin, HTMLTableAdapter):
    # Explicit field mappings (if needed)
    FIELD_CONFIG = {
        "field_mappings": {
            "buying": "cash",
            "tra_buying": "transactional"
        },
        "default_category": "transactional"
    }
```

### Override Strategy Behavior

```python
def _find_tables_resilient(self, soup):
    # Custom strategy order
    # 1. Try custom selector first
    tables = soup.find_all("table", id="exchange-rates")
    if tables:
        return tables, "custom_id"
    
    # 2. Fall back to standard strategies
    return super()._find_tables_resilient(soup)
```

---

## 🚨 Common Issues & Solutions

### Issue: "No tables found" Error

**Cause**: All strategies failed to find tables  
**Solution**:
1. Check if bank moved to JavaScript rendering (→ needs browser automation)
2. Check if data is in JSON API (→ needs JSON adapter)
3. Check if structure is completely new (→ needs custom parser)

### Issue: Field Detection Not Finding Pairs

**Cause**: Field names don't match any pattern  
**Solution**:
```python
# Add custom pattern to detector.py
(r"^your_buy_field$", r"^your_sell_field$")
```

### Issue: Wrong Category Detected

**Cause**: Generic field names (buying/selling) without context  
**Solution**:
```python
# Use context override
for rec in detected_records:
    if rec.category == 'UNKNOWN':
        rec.category = normalize_category("expected_category")
```

---

## 📚 Advanced Usage

### Handle Multiple Table Formats

```python
def _process_tables(self, soup, tables, **kwargs):
    result = ParseResult()
    
    for idx, table in enumerate(tables):
        # Different processing based on table structure
        if self._is_format_a(table):
            records = self._parse_format_a(table)
        elif self._is_format_b(table):
            records = self._parse_format_b(table)
        else:
            result.add_warning(f"table_{idx}:unknown_format")
            continue
        
        result.records.extend(records)
    
    return result
```

### Custom Fingerprinting

```python
def schema_fingerprint(self, raw_content: str) -> str:
    """Custom fingerprint for sensitive detection."""
    soup = BeautifulSoup(raw_content, "html.parser")
    
    # Include specific elements in fingerprint
    signature = {
        "table_count": len(soup.find_all("table")),
        "has_rate_div": bool(soup.find("div", class_="rates")),
        "meta_tags": [m.get("content") for m in soup.find_all("meta")]
    }
    
    payload = json.dumps(signature, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
```

---

## 🎯 Best Practices

### DO:
- ✅ Use `FIELD_CONFIG = {}` to enable auto-detection
- ✅ Let multi-strategy handle table finding
- ✅ Use context override for UNKNOWN categories
- ✅ Test with fixture variations
- ✅ Log unusual situations

### DON'T:
- ❌ Hardcode CSS class names in adapters
- ❌ Assume tables will always exist
- ❌ Bypass field detection with manual parsing
- ❌ Ignore strategy usage logs
- ❌ Skip backward compatibility tests

---

## 📞 Getting Help

### Check Documentation
1. `SCHEMA_CHANGE_STRATEGY.md` - Full strategy document
2. `PHASE_1_COMPLETE_STATUS.md` - Implementation details
3. `MULTI_STRATEGY_FLOW.md` - Visual flow diagrams

### Run Diagnostics
```bash
# Test Phase 1 features
python3 test_phase1_resilience.py

# Check adapter health
python3 -c "from adapters.bank.adapter import BankAdapter; \
            adapter = BankAdapter(); \
            print(adapter.get_adapter_key())"
```

### Review Examples
- `adapters/dashen/adapter.py` - Multi-table HTML
- `adapters/boa/adapter.py` - Section-based categories
- `adapters/wegagen/adapter.py` - JSON API with field detection

---

**Quick Reference Version**: 1.0  
**Last Updated**: October 23, 2026  
**Related**: Phase 1 Schema Change Resilience
