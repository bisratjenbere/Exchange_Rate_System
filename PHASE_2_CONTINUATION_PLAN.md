# Phase 2 Continuation Plan - Ready for Next Session

## Quick Start

**Current Status**: 27% complete (8/30 adapters migrated)  
**Foundation**: ✅ Complete and tested  
**Next Steps**: Continue migrations following established pattern  
**Time Remaining**: ~3-4 hours to complete all 23 remaining adapters

## Immediate Actions for Next Session

### 1. Test Recent Migrations (5 minutes)
```bash
# Verify the 3 newly migrated adapters work
python3 -m pytest tests/ -k "bunna" -v
python3 -m pytest tests/ -k "amhara" -v  
python3 -m pytest tests/test_m8_wave2_adapters.py -k "wegagen" -v
```

### 2. Continue with JSON Adapters (30-45 minutes)
These are the easiest - follow CBE/ADIB/Wegagen pattern:

**Rammis** (`adapters/rammis/adapter.py`):
- Type: JSONAdapter
- Pattern: Similar to CBE
- Test: `python3 -m pytest tests/ -k "rammis" -v`

**CBO** (`adapters/cbo/adapter.py`):
- Type: JSONAdapter  
- Pattern: Similar to ADIB
- Test: `python3 -m pytest tests/ -k "cbo" -v`

**Global** (`adapters/global_/adapter.py`):
- Type: JSONAdapter
- Pattern: Similar to CBE
- Test: `python3 -m pytest tests/ -k "global" -v`

**Siinqee** (`adapters/siinqee/adapter.py`):
- Type: JSONAdapter
- Pattern: Similar to Wegagen (Strapi)
- Test: `python3 -m pytest tests/ -k "siinqee" -v`

### 3. Continue with HTMLTable Adapters (1-1.5 hours)
These follow DBE/Bunna/Amhara pattern:

**Priority Order**:
1. Dashen - Standard single table
2. Enat - Multi-table
3. Berhan - Standard single table
4. Hibret - Single table with code aliases
5. Nib - Multi-table (3 tables)
6. Omo - Multi-table with per-table dates
7. Tsehay - Multi-table
8. Goh Betoch - Standard
9. Sidama - Standard

### 4. Complete with HTMLText Adapters (1-1.5 hours)
All follow Ahadu pattern (simplest):

1. Awash
2. Abay
3. Oromia
4. Zemen
5. Anbesa
6. Gadaa
7. Shabelle
8. Tsedey
9. Zamzam
10. Siket

## Migration Template (Copy-Paste Ready)

### For JSONAdapter

```python
from adapters.base import JSONAdapter, ParseResult

class <Bank>Adapter(JSONAdapter):
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_data(self, data, **options) -> ParseResult:
        result = ParseResult()
        
        # Validation
        if not isinstance(data, <expected_type>):
            result.add_error(f"<Bank>: expected <type>, got {type(data).__name__}")
            return result
        
        # Parse (reuse existing _parse_item or similar helpers)
        for item in data:
            records = _parse_item(item)
            result.records.extend(records)
        
        return result

# Backward compatibility
def parse(raw_json: str) -> list:
    adapter = <Bank>Adapter()
    result = adapter.parse(raw_json)
    if not result.is_success():
        raise ValueError(result.errors[0] if result.errors else "Parse failed")
    return result.records

def schema_fingerprint(raw_json: str) -> str:
    adapter = <Bank>Adapter()
    return adapter.schema_fingerprint(raw_json)
```

### For HTMLTableAdapter

```python
from adapters.base import HTMLTableAdapter, ParseResult

class <Bank>Adapter(HTMLTableAdapter):
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, tables, **options) -> ParseResult:
        result = ParseResult()
        soup = options.get('soup')  # If needed for date parsing
        
        if not tables:
            result.add_error("table_0:missing")
            return result
        
        try:
            records = _parse_table(tables[0])  # Reuse existing helper
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")
        
        return result

# Backward compatibility
def parse(raw_html: str) -> tuple:
    adapter = <Bank>Adapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    adapter = <Bank>Adapter()
    return adapter.schema_fingerprint(raw_html)
```

### For HTMLTextAdapter

```python
from adapters.base import HTMLTextAdapter, ParseResult

class <Bank>Adapter(HTMLTextAdapter):
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_soup(self, soup, **options) -> ParseResult:
        result = ParseResult()
        
        # Parse (reuse existing helpers)
        text = soup.get_text()
        records = _extract_records(text)  # Reuse existing helper
        result.records.extend(records)
        
        return result

# Backward compatibility  
def parse(raw_html: str) -> tuple:
    adapter = <Bank>Adapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    adapter = <Bank>Adapter()
    return adapter.schema_fingerprint(raw_html)
```

## Checklist Per Adapter

- [ ] 1. Read existing adapter file
- [ ] 2. Identify type (JSON/HTMLTable/HTMLText)
- [ ] 3. Add base class import
- [ ] 4. Create `<Bank>Adapter` class
- [ ] 5. Implement required methods (`get_source_url`, `get_adapter_key`, `_process_*`)
- [ ] 6. Move parse logic into `_process_*` method
- [ ] 7. Reuse existing helper functions unchanged
- [ ] 8. Add backward compatibility wrapper functions
- [ ] 9. Test: `python3 -c "from adapters.<bank>.adapter import <Bank>Adapter; print('OK')"`
- [ ] 10. Test: `python3 -m pytest tests/ -k "<bank>" -v`

## Common Patterns

### Pattern 1: JSON Array at Top Level (CBE, ADIB, Rammis)
```python
def _process_data(self, data, **options) -> ParseResult:
    result = ParseResult()
    if not isinstance(data, list):
        result.add_error(f"Expected list, got {type(data).__name__}")
        return result
    for item in data:
        records = _parse_item(item)  # existing function
        result.records.extend(records)
    return result
```

### Pattern 2: Strapi v4 Envelope (Wegagen, Siinqee)
```python
def _process_data(self, data, **options) -> ParseResult:
    result = ParseResult()
    if not isinstance(data, dict) or "data" not in data:
        result.add_error("Missing 'data' key")
        return result
    items = data["data"]
    for item in items:
        records = _parse_item(item)  # existing function
        result.records.extend(records)
    return result
```

### Pattern 3: Single HTML Table (DBE, Dashen)
```python
def _process_tables(self, tables, **options) -> ParseResult:
    result = ParseResult()
    if not tables:
        result.add_error("table_0:missing")
        return result
    try:
        records = _parse_table(tables[0])  # existing function
        result.records.extend(records)
    except Exception as exc:
        result.add_error(f"table_0:{exc}")
    return result
```

### Pattern 4: Multi-Table (Amhara, Nib, Omo)
```python
def _process_tables(self, tables, **options) -> ParseResult:
    result = ParseResult()
    soup = options.get('soup')
    
    if len(tables) < 2:
        result.add_error("table_1:missing")
    
    # Table 0
    try:
        records = _parse_table_0(tables[0])  # existing
        result.records.extend(records)
    except Exception as exc:
        result.add_error(f"table_0:{exc}")
    
    # Table 1
    if len(tables) >= 2:
        try:
            records = _parse_table_1(tables[1])  # existing
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_1:{exc}")
    
    return result
```

### Pattern 5: Text Extraction (Ahadu, all HTMLText adapters)
```python
def _process_soup(self, soup, **options) -> ParseResult:
    result = ParseResult()
    text = soup.get_text()
    records = _extract_records(text)  # existing function
    result.records.extend(records)
    return result
```

## Testing Strategy

### After Each Adapter
```bash
python3 -c "from adapters.<bank>.adapter import <Bank>Adapter; print('OK')"
python3 -m pytest tests/ -k "<bank>" -v
```

### After Each Batch (4-5 adapters)
```bash
python3 -m pytest tests/ -v --tb=short | tail -20
```

### Before Completing Phase 2
```bash
python3 -m pytest tests/ -q
# Should see 429 tests collected, check pass rate
```

## Troubleshooting

### Issue: Import Error
**Solution**: Check base class import path:
```python
from adapters.base import JSONAdapter, ParseResult  # Correct
from adapters.base import HTMLTableAdapter, ParseResult  # Correct
from adapters.base import HTMLTextAdapter, ParseResult  # Correct
```

### Issue: Tests Fail After Migration
**Solution**: 
1. Check backward compatibility wrapper matches old signature
2. Verify helper functions still work (they should be unchanged)
3. Check if adapter returns list vs tuple

### Issue: Duplicate schema_fingerprint
**Solution**: Keep only the wrapper function:
```python
def schema_fingerprint(raw_content: str) -> str:
    adapter = <Bank>Adapter()
    return adapter.schema_fingerprint(raw_content)
```

## Files to Reference

- **Migration Guide**: `docs/handoff/PHASE_2_MIGRATION_GUIDE.md`
- **Base Classes**: `adapters/base.py`
- **Reference Implementations**:
  - JSONAdapter: `adapters/cbe/adapter.py`, `adapters/adib/adapter.py`, `adapters/wegagen/adapter.py`
  - HTMLTableAdapter: `adapters/dbe/adapter.py`, `adapters/bunna/adapter.py`, `adapters/amhara/adapter.py`
  - HTMLTextAdapter: `adapters/ahadu/adapter.py`

## Success Criteria

- [ ] All 30 adapters use base classes
- [ ] All 429 tests pass
- [ ] ~30% code reduction achieved
- [ ] Backward compatibility maintained
- [ ] Documentation updated

## Estimated Time Remaining

- **JSON adapters** (4 remaining): 30-45 minutes
- **HTMLTable adapters** (9 remaining): 1-1.5 hours
- **HTMLText adapters** (10 remaining): 1-1.5 hours
- **Testing & validation**: 30 minutes
- **Total**: 3-4 hours

## Ready to Continue?

When you're ready to continue, start with:
1. Test the 3 newly migrated adapters (Bunna, Amhara, Wegagen)
2. Pick Rammis as the next adapter (JSONAdapter, similar to CBE)
3. Follow the JSONAdapter template above
4. Test immediately after migration

The pattern is proven, the foundation is solid, and you have all the tools needed to complete Phase 2 efficiently. Good luck!
