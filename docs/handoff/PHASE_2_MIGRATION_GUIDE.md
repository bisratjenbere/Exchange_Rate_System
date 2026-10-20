# Phase 2 Adapter Migration Guide

## Overview

This document guides the completion of Phase 2: migrating the remaining 26 adapters to use the base classes established in Phase 1.

## Current Status

### ✅ Phase 1 Complete (Foundation)
- **Base Classes**: `adapters/base.py` - All 4 adapter types
- **HTTP Client**: `http_clients/client.py` - Full abstraction with retry logic
- **Reference Implementations**: 3 adapters fully migrated and tested
  - CBE (JSONAdapter) - 30/30 tests passing
  - DBE (HTMLTableAdapter) - 9/9 tests passing  
  - Ahadu (HTMLTextAdapter) - 11/11 tests passing

### 🔄 Phase 2 In Progress

**Completed** (4 adapters):
- ✅ ADIB - JSONAdapter (29 tests passing)
- ✅ Bunna - HTMLTableAdapter (refactored)
- ✅ Amhara - HTMLTableAdapter (refactored)

**Remaining** (26 adapters):
- Nib, Omo, Wegagen, Hibret (next batch)
- Dashen, CBO, Berhan, Enat (batch 2)
- Tsehay, Rammis, Global, Goh Betoch (batch 3)
- Siinqee, Sidama, Awash, Abay (batch 4)
- Oromia, Zemen, Anbesa, Gadaa (batch 5)
- Shabelle, Tsedey, Zamzam, Siket (batch 6)

## Migration Pattern (3 Steps per Adapter)

### Step 1: Identify Adapter Type

Determine which base class to use:

**JSONAdapter** - For JSON APIs:
- CBE, ADIB, Wegagen, Rammis, CBO, Global, Siinqee

**HTMLTableAdapter** - For HTML with tables:
- DBE, Bunna, Amhara, Nib, Omo, Hibret, Dashen, Enat, Berhan, Tsehay, Goh Betoch, Sidama

**HTMLTextAdapter** - For text extraction:
- Ahadu, Awash, Abay, Oromia, Zemen, Anbesa, Gadaa, Shabelle, Tsedey, Zamzam, Siket

### Step 2: Refactor Adapter Class

**For JSONAdapter:**

```python
from adapters.base import JSONAdapter, ParseResult

class <Bank>Adapter(JSONAdapter):
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_data(self, data, **options) -> ParseResult:
        """Extract AdapterRecords from parsed JSON data."""
        result = ParseResult()
        
        # Validation
        if not isinstance(data, <expected_type>):
            result.add_error(f"Expected {<expected_type>}, got {type(data)}")
            return result
        
        # Parse logic (move existing code here)
        for item in data:
            records = _parse_item(item)  # existing helper
            result.records.extend(records)
        
        return result
```

**For HTMLTableAdapter:**

```python
from adapters.base import HTMLTableAdapter, ParseResult

class <Bank>Adapter(HTMLTableAdapter):
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, tables, **options) -> ParseResult:
        """Extract AdapterRecords from parsed HTML tables."""
        result = ParseResult()
        
        # Get soup if needed for date parsing
        soup = options.get('soup')
        
        if not tables:
            result.add_error("table_0:missing")
            return result
        
        # Parse logic (move existing code here)
        try:
            records = _parse_table(tables[0])
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")
        
        return result
```

**For HTMLTextAdapter:**

```python
from adapters.base import HTMLTextAdapter, ParseResult

class <Bank>Adapter(HTMLTextAdapter):
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_soup(self, soup, **options) -> ParseResult:
        """Extract AdapterRecords from BeautifulSoup object."""
        result = ParseResult()
        
        # Parse logic (move existing code here)
        text = soup.get_text()
        records = _extract_records(text)
        result.records.extend(records)
        
        return result
```

### Step 3: Add Backward Compatibility Wrapper

**For adapters that return lists:**

```python
def parse(raw_content: str) -> list:
    """Backward compatibility wrapper."""
    adapter = <Bank>Adapter()
    result = adapter.parse(raw_content)
    
    # Maintain old behavior: raise ValueError on errors
    if not result.is_success():
        raise ValueError(result.errors[0] if result.errors else "Parse failed")
    
    return result.records

def schema_fingerprint(raw_content: str) -> str:
    """Backward compatibility wrapper."""
    adapter = <Bank>Adapter()
    return adapter.schema_fingerprint(raw_content)
```

**For adapters that return tuples:**

```python
def parse(raw_content: str) -> tuple:
    """Backward compatibility wrapper."""
    adapter = <Bank>Adapter()
    result = adapter.parse(raw_content)
    return result.records, result.errors

def schema_fingerprint(raw_content: str) -> str:
    """Backward compatibility wrapper."""
    adapter = <Bank>Adapter()
    return adapter.schema_fingerprint(raw_content)
```

## Verification Steps

After migrating each adapter:

1. **Import Test**: `python3 -c "from adapters.<bank>.adapter import <Bank>Adapter, parse; print('OK')"`
2. **Run Tests**: `python3 -m pytest tests/ -k "<bank>" -v`
3. **Check Backward Compatibility**: Existing `parse()` function must work unchanged

## Adapter Classification Reference

### JSON Adapters (7)
- **CBE** ✅ - Migrated (reference)
- **ADIB** ✅ - Migrated
- **Wegagen** - Strapi v4 envelope
- **Rammis** - JSON API
- **CBO** - JSON API
- **Global** - JSON API
- **Siinqee** - JSON API

### HTML Table Adapters (12)
- **DBE** ✅ - Migrated (reference)
- **Bunna** ✅ - Migrated
- **Amhara** ✅ - Migrated
- **Nib** - Multi-table (3 tables)
- **Omo** - Multi-table with per-table dates
- **Hibret** - Single table, date in page
- **Dashen** - Single table
- **Enat** - Multi-table
- **Berhan** - Single table
- **Tsehay** - Multi-table
- **Goh Betoch** - Single table
- **Sidama** - Single table

### HTML Text Adapters (11)
- **Ahadu** ✅ - Migrated (reference)
- **Awash** - Text extraction
- **Abay** - Text extraction
- **Oromia** - Text extraction
- **Zemen** - Text extraction
- **Anbesa** - Text extraction
- **Gadaa** - Text extraction
- **Shabelle** - Text extraction
- **Tsedey** - Text extraction
- **Zamzam** - Text extraction
- **Siket** - Text extraction

## Common Issues & Solutions

### Issue: Duplicate schema_fingerprint Functions
**Solution**: Remove all old implementations, keep only the wrapper:
```python
def schema_fingerprint(raw_content: str) -> str:
    adapter = <Bank>Adapter()
    return adapter.schema_fingerprint(raw_content)
```

### Issue: Parse Returns Tuple vs List
**Solution**: Match the existing return type in the wrapper function.

### Issue: HTML Adapters Need Soup for Date Parsing
**Solution**: Access soup from options:
```python
def _process_tables(self, tables, **options) -> ParseResult:
    soup = options.get('soup')
    effective_date = _parse_date(soup) if soup else None
```

### Issue: Custom schema_fingerprint Logic
**Solution**: Override the method in the adapter class if needed:
```python
class <Bank>Adapter(JSONAdapter):
    def schema_fingerprint(self, raw_content: str) -> str:
        # Custom logic here
        pass
```

## Testing Strategy

1. **Per-Adapter**: Test immediately after refactoring
2. **Batch Testing**: After each group of 4-5 adapters
3. **Full Suite**: Run all 429 tests at the end

## Expected Outcomes

- **Code Reduction**: ~30% fewer lines in adapter code
- **Consistency**: All adapters follow same pattern
- **Testability**: Can use MockHttpClient for all adapters
- **Maintainability**: Changes to HTTP logic or base parsing happen in one place

## Next Steps

1. Continue with Wegagen (JSONAdapter)
2. Then Nib, Omo (HTMLTableAdapter)
3. Then Hibret (HTMLTableAdapter)
4. Continue through remaining adapters in batches
5. Run full test suite after each batch
6. Mark tasks complete in `.kiro/specs/adapter-base-classes-and-http-abstraction/tasks.md`
