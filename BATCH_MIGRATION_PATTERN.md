# Batch Migration Pattern for HTML Table Adapters

## Universal Transformation

### Before (Old Pattern)
```python
class BankAdapter(HTMLTableAdapter):
    def _process_tables(self, soup, tables, **kwargs):
        # Manual cell extraction
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        buying = _safe_rate(cells[2])
        selling = _safe_rate(cells[3])
        
        # Manual record creation
        records.append(AdapterRecord(
            source_currency_code=currency_code,
            category=hardcoded_category,
            buying_rate=buying,
            selling_rate=selling,
            ...
        ))
```

### After (Universal Pattern)
```python
from field_detection.mixin import FieldStructureMixin

class BankAdapter(FieldStructureMixin, HTMLTableAdapter):
    FIELD_CONFIG = {}  # Empty - auto-detect
    
    def _process_tables(self, soup, tables, **kwargs):
        # Convert cells to dict
        row_dict = {
            "buying": cells[2],      # or "cash_buying", "transaction_buying", etc.
            "selling": cells[3],      # based on table structure
        }
        
        # Use field detection
        detected_records = self.detect_and_emit(
            data=row_dict,
            currency=currency_code,
            effective_date=date,
            effective_date_basis=basis
        )
        
        # Context-based override if needed
        for rec in detected_records:
            if rec.category == 'UNKNOWN':
                rec.category = determine_from_context()
```

## Key Benefits
1. **No manual record creation** - field detection handles it
2. **Dynamic category detection** - from field names
3. **Future-proof** - adapts to new categories automatically
4. **Consistent** - all adapters use same pattern

## Migration Steps (5 minutes per adapter)
1. Add mixin import and inheritance
2. Add `FIELD_CONFIG = {}`
3. Replace manual parsing with dict creation
4. Call `detect_and_emit()`
5. Handle UNKNOWN if needed
6. Remove old helper functions

## Completed: 10/32 (31%)
- Phase 1 API: 4/4 ✅
- HTML: 2/21 (Oromia, Dashen) ✅
- Remaining: 22 adapters

## Ready for Batch Migration
Similar simple HTML tables - can do 5-10 at once:
- Omo, Siinqee, Siket, Zamzam (just scanned)
- Shabelle, Berhan, Tsedey, Sidama (similar structure expected)
