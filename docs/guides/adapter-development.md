# Adapter Development Guide

This guide explains how to create and maintain bank adapters for the Ethiopian Bank Exchange Rate system.

## Table of Contents

1. [Overview](#overview)
2. [Choosing the Right Base Class](#choosing-the-right-base-class)
3. [JSONAdapter Guide](#jsonadapter-guide)
4. [HTMLTableAdapter Guide](#htmltableadapter-guide)
5. [HTMLTextAdapter Guide](#htmltextadapter-guide)
6. [Custom BankAdapter Guide](#custom-bankadapter-guide)
7. [Backward Compatibility](#backward-compatibility)
8. [Testing Your Adapter](#testing-your-adapter)
9. [Common Patterns](#common-patterns)
10. [Troubleshooting](#troubleshooting)

---

## Overview

All bank adapters inherit from one of four base classes in `adapters/base.py`:

- **`JSONAdapter`** - For JSON API sources
- **`HTMLTableAdapter`** - For HTML pages with `<table>` elements
- **`HTMLTextAdapter`** - For HTML pages with text-embedded rates (no tables)
- **`BankAdapter`** - Direct inheritance for custom implementations

The base classes handle common operations (parsing, error handling, helpers) so you only implement bank-specific extraction logic.

**Key Principle**: Adapters output `AdapterRecord` objects in a normalized format. The pipeline never knows which bank produced a record.

---

## Choosing the Right Base Class

Use this decision tree:

```
Is the source a JSON API?
├─ YES → Use JSONAdapter
└─ NO → Is the data in HTML <table> elements?
    ├─ YES → Use HTMLTableAdapter
    └─ NO → Is the data in page text/divs?
        ├─ YES → Use HTMLTextAdapter
        └─ NO → Use BankAdapter (custom parse logic)
```

### Examples by Base Class

| Base Class | Example Banks | Use When |
|-----------|---------------|----------|
| `JSONAdapter` | CBE, Rammis, ADIB, Wegagen, Zemen | Source returns JSON from API |
| `HTMLTableAdapter` | Dashen, NIB, Bunna, CBO, Zamzam | Rates are in HTML `<table>` elements |
| `HTMLTextAdapter` | Ahadu, Enat, Berhan, Sidama, Anbesa | Rates in paragraphs, divs, or inline text |
| `BankAdapter` | Shabelle, Tsedey | Complex custom structures |

---

## JSONAdapter Guide

### When to Use

- Source is a REST API returning JSON
- Examples: `{"rates": [...]}`, Strapi CMS, WordPress AJAX

### Required Methods

```python
from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord

class MyBankAdapter(JSONAdapter):
    def get_source_url(self) -> str:
        return "https://mybank.com/api/rates"
    
    def get_adapter_key(self) -> str:
        return "mybank_api"
    
    def _process_data(self, data, **kwargs) -> ParseResult:
        """Extract records from parsed JSON."""
        result = ParseResult()
        
        # Your extraction logic here
        for item in data.get("rates", []):
            record = AdapterRecord(
                source_currency_code=item["currency"],
                category=item["category"],
                buying_rate=self._safe_rate(item["buying"]),
                selling_rate=self._safe_rate(item["selling"]),
                effective_date=self._parse_iso_date(item["date"]),
                effective_date_basis="source_published",
                # ... other fields
            )
            result.records.append(record)
        
        return result
```

### What JSONAdapter Provides

- **Automatic JSON parsing**: `parse()` calls `json.loads()` and passes result to your `_process_data()`
- **Error handling**: Invalid JSON automatically returns `ParseResult` with error
- **Default fingerprinting**: Hashes top-level JSON keys (override `schema_fingerprint()` for custom logic)
- **Helper methods**: `_safe_rate()`, `_parse_iso_date()`, `_rate_text()`

### Real Example: CBE Adapter

```python
class CBEAdapter(JSONAdapter):
    def get_source_url(self) -> str:
        return "https://combanketh.et/cbeapi/daily-exchange-rates/"
    
    def get_adapter_key(self) -> str:
        return "cbe_api"
    
    def _process_data(self, data, **kwargs) -> ParseResult:
        result = ParseResult()
        
        for publication in data:
            pub_key = publication["_id"]
            date_str = publication["Date"]
            effective_date = self._parse_iso_date(date_str)
            
            for rate_item in publication["ExchangeRate"]:
                currency = rate_item["CurrencyCode"]
                
                # Cash record
                if rate_item["CashBuying"] or rate_item["CashSelling"]:
                    result.records.append(AdapterRecord(
                        source_currency_code=currency,
                        category="cash",
                        buying_rate=self._safe_rate(rate_item["CashBuying"]),
                        selling_rate=self._safe_rate(rate_item["CashSelling"]),
                        effective_date=effective_date,
                        effective_date_basis="source_published",
                        source_publication_key=pub_key,
                        # ... more fields
                    ))
                
                # Transactional record
                # ... similar logic
        
        return result
```

---

## HTMLTableAdapter Guide

### When to Use

- Source is HTML page with rates in `<table>` elements
- Tables can be multi-table (one per category) or wide-table (all categories in columns)

### Required Methods

```python
from adapters.base import HTMLTableAdapter, ParseResult
from domain.records import AdapterRecord
from bs4 import BeautifulSoup

class MyBankAdapter(HTMLTableAdapter):
    def get_source_url(self) -> str:
        return "https://mybank.com/rates"
    
    def get_adapter_key(self) -> str:
        return "mybank_html"
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        """Extract records from HTML tables."""
        result = ParseResult()
        
        # Your table parsing logic here
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:  # Skip header
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                
                record = AdapterRecord(
                    source_currency_code=cells[0],
                    category="transactional",
                    buying_rate=self._safe_rate(cells[1]),
                    selling_rate=self._safe_rate(cells[2]),
                    # ... other fields
                )
                result.records.append(record)
        
        return result
```

### What HTMLTableAdapter Provides

- **Automatic HTML parsing**: Uses BeautifulSoup
- **Table extraction**: Finds all `<table>` elements, passes to your `_process_tables()`
- **Error handling**: "No tables found" automatically handled
- **Default fingerprinting**: Hashes table count + header cells
- **Pre-parsed soup and tables**: No need to call `BeautifulSoup()` or `find_all("table")`

### Real Example: Dashen Adapter (Multi-Table)

```python
class DashenAdapter(HTMLTableAdapter):
    def get_source_url(self) -> str:
        return "https://dashenbanksc.com/daily-exchange-rate/"
    
    def get_adapter_key(self) -> str:
        return "dashen_html"
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        result = ParseResult()
        
        # Table 0: Cash rates (no date)
        result.records.extend(_parse_cash_table(tables[0]))
        
        # Table 1: Transactional rates (no date)
        result.records.extend(_parse_txn_table(tables[1]))
        
        # Table 2: Weighted average (date in header)
        weighted_date = _extract_date_from_header(tables[2])
        result.records.extend(_parse_weighted_table(tables[2], weighted_date))
        
        return result
```

### Pattern: Wide Table with Multiple Categories

```python
def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
    result = ParseResult()
    table = tables[0]  # Single wide table
    rows = table.find_all("tr")
    
    # Parse header to find column positions
    # Row 0: Category labels (CASH | TRANSACTION | AVERAGE)
    # Row 1: Buying | Selling | Buying | Selling | ...
    
    for row in rows[2:]:  # Skip two header rows
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        currency = cells[0]
        
        # Emit cash record (columns 1-2)
        result.records.append(AdapterRecord(
            source_currency_code=currency,
            category="cash",
            buying_rate=self._safe_rate(cells[1]),
            selling_rate=self._safe_rate(cells[2]),
            # ...
        ))
        
        # Emit transactional record (columns 3-4)
        result.records.append(AdapterRecord(
            source_currency_code=currency,
            category="transactional",
            buying_rate=self._safe_rate(cells[3]),
            selling_rate=self._safe_rate(cells[4]),
            # ...
        ))
    
    return result
```

---

## HTMLTextAdapter Guide

### When to Use

- Source is HTML page with rates embedded in text (not in tables)
- Rates are in paragraphs, divs, or inline text
- Requires regex or text pattern matching

### Required Methods

```python
from adapters.base import HTMLTextAdapter, ParseResult
from domain.records import AdapterRecord
from bs4 import BeautifulSoup
import re

class MyBankAdapter(HTMLTextAdapter):
    def get_source_url(self) -> str:
        return "https://mybank.com/rates"
    
    def get_adapter_key(self) -> str:
        return "mybank_text"
    
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **kwargs) -> ParseResult:
        """Extract records from normalized text."""
        result = ParseResult()
        
        # Your text extraction logic here
        pattern = r'([A-Z]{3})\s+Buying:\s*([\d.]+)\s+Selling:\s*([\d.]+)'
        for match in re.finditer(pattern, text):
            currency, buying, selling = match.groups()
            
            record = AdapterRecord(
                source_currency_code=currency,
                category="transactional",
                buying_rate=self._safe_rate(buying),
                selling_rate=self._safe_rate(selling),
                # ... other fields
            )
            result.records.append(record)
        
        return result
```

### What HTMLTextAdapter Provides

- **Automatic HTML parsing**: Uses BeautifulSoup
- **Text normalization**: Whitespace collapsed to single spaces
- **Both text and soup**: Can use regex on text OR DOM queries on soup
- **Pre-processed input**: Text ready for pattern matching

### Real Example: Ahadu Adapter

```python
class AhaduAdapter(HTMLTextAdapter):
    def get_source_url(self) -> str:
        return "https://ahadubank.com/"
    
    def get_adapter_key(self) -> str:
        return "ahadu_html"
    
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **kwargs) -> ParseResult:
        result = ParseResult()
        category = kwargs.get("category", "UNKNOWN")
        
        # Extract date from page text
        date_match = re.search(r'(\w+ \d{1,2},? \d{4})', text)
        effective_date = None
        if date_match:
            effective_date = _parse_date_string(date_match.group(1))
        
        # Extract rates: "USD ... Buying 161.23 ... Selling 164.56"
        pattern = r'([A-Z]{3})[^0-9]*Buying[^0-9]*([\d.]+)[^0-9]*Selling[^0-9]*([\d.]+)'
        
        for match in re.finditer(pattern, text):
            currency, buying, selling = match.groups()
            
            result.records.append(AdapterRecord(
                source_currency_code=currency,
                category=category,
                buying_rate=self._safe_rate(buying),
                selling_rate=self._safe_rate(selling),
                effective_date=effective_date,
                effective_date_basis="source_published" if effective_date else "collection_date_fallback",
                # ...
            ))
        
        return result
    
    def requires_category(self) -> bool:
        return True  # Type G adapters need category parameter
```

---

## Custom BankAdapter Guide

### When to Use

- Source structure doesn't fit JSON/table/text patterns
- Need complete control over parsing logic
- Examples: JSON embedded in HTML, complex div structures

### Required Methods

```python
from adapters.base import BankAdapter, ParseResult
from domain.records import AdapterRecord

class MyBankAdapter(BankAdapter):
    def get_source_url(self) -> str:
        return "https://mybank.com/rates"
    
    def get_adapter_key(self) -> str:
        return "mybank_custom"
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        """Custom parse implementation."""
        result = ParseResult()
        
        # Your custom logic here
        # Must return ParseResult
        
        return result
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """Custom fingerprinting logic."""
        # Return SHA256 hash of structural signature
        import hashlib
        return hashlib.sha256(b"custom_signature").hexdigest()
```

### Real Example: Tsedey Adapter (JSON in HTML)

```python
class TsedeyAdapter(BankAdapter):
    def get_source_url(self) -> str:
        return "https://www.tsedeybank.com.et/"
    
    def get_adapter_key(self) -> str:
        return "tsedey_html"
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        result = ParseResult()
        seen = set()
        
        # Extract JSON records embedded in HTML via regex
        pattern = re.compile(r'\{"id":\d+,"name":"[^"]+","code":"[A-Z]{3}"[^}]+\}')
        
        for match in pattern.finditer(raw_content):
            try:
                row = json.loads(match.group())
                code = row.get("code", "").strip()
                category_raw = row.get("category", "").lower()
                
                # Map source category to our category
                category = "transactional" if category_raw == "non-cash" else "cash"
                
                dedup_key = f"{code}:{category}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                
                result.records.append(AdapterRecord(
                    source_currency_code=code,
                    category=category,
                    buying_rate=self._safe_rate(row.get("buying_rate")),
                    selling_rate=self._safe_rate(row.get("selling_rate")),
                    effective_date=self._parse_iso_date(row.get("updated_at", "")),
                    effective_date_basis="source_inferred",
                    # ...
                ))
            except Exception as exc:
                result.add_error(f"record:{match.group()[:40]}:{exc}")
        
        return result
```

---

## HTTP Client Abstraction

All adapters fetch data from external sources (APIs, websites). The HTTP client abstraction in `http_clients/http_client.py` provides a testable, configurable way to handle HTTP requests.

### The HttpClient Interface

All HTTP clients implement the `HttpClient` abstract interface:

```python
from http_clients.http_client import HttpClient, HttpResponse

class MyAdapter(BankAdapter):
    def __init__(self, http_client: HttpClient):
        self.http_client = http_client
    
    def fetch_and_parse(self) -> ParseResult:
        response = self.http_client.fetch(self.get_source_url())
        
        if not response.is_success():
            result = ParseResult()
            result.add_error(f"Fetch failed: {response.error}")
            return result
        
        return self.parse(response.content)
```

### HttpResponse Structure

All fetch operations return an `HttpResponse`:

```python
@dataclass
class HttpResponse:
    content: str          # Response body
    status_code: int      # HTTP status (200, 404, etc.)
    url: str             # The URL that was fetched
    error: Optional[str]  # Error message if fetch failed, None otherwise
    
    def is_success(self) -> bool:
        return self.error is None and 200 <= self.status_code < 300
```

**Key principle**: HTTP clients never raise exceptions - they always return an `HttpResponse` with the `error` field populated on failure.

---

### RequestsHttpClient (Production)

Production HTTP client with retry logic and configurable timeouts.

#### Features

- Configurable timeout, retries, and retry delay
- Exponential backoff on retry (delay × 2^attempt)
- Automatic User-Agent header
- Support for POST requests, custom headers, SSL verification
- Never raises exceptions

#### Usage

```python
from http_clients.http_client import RequestsHttpClient

# Default configuration
client = RequestsHttpClient()

# Custom configuration
client = RequestsHttpClient(
    timeout=30.0,        # Request timeout in seconds (default: 15.0)
    max_retries=3,       # Number of retries on timeout/connection error (default: 2)
    retry_delay=5.0,     # Base delay between retries in seconds (default: 2.0)
    user_agent="MyCustomAgent/2.0"
)

# Simple GET request
response = client.fetch("https://example.com/api/rates")
if response.is_success():
    data = response.content
else:
    print(f"Error: {response.error}")

# POST request with custom headers
response = client.fetch(
    "https://example.com/api/submit",
    post_data={"currency": "USD"},
    headers={"Authorization": "Bearer token123"}
)

# Disable SSL verification (not recommended for production)
response = client.fetch("https://example.com", ssl_verify=False)
```

#### Retry Behavior

RequestsHttpClient retries on:
- **Timeout errors**: Retries with exponential backoff
- **Connection errors**: Retries with exponential backoff
- **Other errors**: No retry (returns error immediately)

Example retry sequence with `max_retries=2`, `retry_delay=2.0`:
1. Initial attempt fails (timeout)
2. Wait 2.0s, retry (timeout)
3. Wait 4.0s, retry (timeout)
4. Return error

#### Example in Adapter

```python
from adapters.base import JSONAdapter, ParseResult
from http_clients.http_client import RequestsHttpClient

class MyBankAdapter(JSONAdapter):
    def __init__(self, http_client: RequestsHttpClient = None):
        self.http_client = http_client or RequestsHttpClient(timeout=20.0)
    
    def fetch_and_parse(self) -> ParseResult:
        response = self.http_client.fetch(self.get_source_url())
        
        if not response.is_success():
            result = ParseResult()
            result.add_error(f"HTTP error: {response.error}")
            return result
        
        return self.parse(response.content)
```

---

### MockHttpClient (Testing)

Test HTTP client that returns predefined responses based on URL pattern matching.

#### Features

- URL pattern matching (exact or substring)
- Tracks fetch count and last URL for assertions
- Runtime response configuration
- Returns 404 for non-configured URLs

#### Usage

```python
from http_clients.http_client import MockHttpClient

# Configure responses at initialization
client = MockHttpClient({
    "example.com": '{"rates": [{"currency": "USD", "rate": 100.0}]}',
    "bank.et": '<html><table>rates</table></html>'
})

# Pattern matching (substring)
response = client.fetch("https://example.com/api/rates")  # Matches "example.com"
assert response.is_success()
assert '"rates"' in response.content

# Add responses at runtime
client.configure_response("newbank.com", '{"data": []}')

# Test assertions
assert client.fetch_count == 1
assert client.last_url == "https://example.com/api/rates"

# Non-configured URL returns 404
response = client.fetch("https://unknown.com")
assert response.status_code == 404
assert not response.is_success()
```

#### Example in Tests

```python
# tests/test_mybank_adapter.py

from adapters.mybank.adapter import MyBankAdapter
from http_clients.http_client import MockHttpClient

def test_mybank_adapter_success():
    # Prepare mock response
    mock_http = MockHttpClient({
        "mybank.com": '{"rates": [{"currency": "USD", "buying": 100.0, "selling": 102.0}]}'
    })
    
    # Inject mock into adapter
    adapter = MyBankAdapter(http_client=mock_http)
    result = adapter.fetch_and_parse()
    
    # Assert results
    assert result.is_success()
    assert len(result.records) == 1
    assert mock_http.fetch_count == 1

def test_mybank_adapter_http_error():
    # Mock returns 404
    mock_http = MockHttpClient()  # Empty responses
    
    adapter = MyBankAdapter(http_client=mock_http)
    result = adapter.fetch_and_parse()
    
    # Verify error handling
    assert not result.is_success()
    assert len(result.errors) > 0
    assert "HTTP error" in result.errors[0]
```

---

### FileHttpClient (Development)

File-based HTTP client that loads responses from fixture files based on URL domain.

#### Features

- Maps URL domains to fixture files
- Tries both `.json` and `.html` extensions
- No network requests - useful for development and offline testing
- Returns 404 when fixture not found

#### Usage

```python
from http_clients.http_client import FileHttpClient

# Initialize with fixtures directory
client = FileHttpClient(fixtures_dir="fixtures")

# URL domain mapping
# "https://combanketh.et/api" → "fixtures/combanketh_et.json" or "fixtures/combanketh_et.html"
response = client.fetch("https://combanketh.et/api/rates")

if response.is_success():
    print(response.content)  # Contents of combanketh_et.json
else:
    print(f"Fixture not found: {response.error}")
```

#### Fixture File Naming

FileHttpClient extracts the domain from the URL and converts it to a filename:

| URL | Fixture Files Tried |
|-----|---------------------|
| `https://combanketh.et/api` | `combanketh_et.json`, `combanketh_et.html` |
| `https://dashenbanksc.com/rates` | `dashenbanksc_com.json`, `dashenbanksc_com.html` |
| `http://bank.example.org/data` | `bank_example_org.json`, `bank_example_org.html` |

**Rule**: Replace dots (`.`) with underscores (`_`) in the domain name.

#### Example Directory Structure

```
fixtures/
├── combanketh_et.json          # CBE adapter
├── dashenbanksc_com.html       # Dashen adapter
├── ahadubank_com.html          # Ahadu adapter
└── rammis_com.json             # Rammis adapter
```

#### Example in Development

```python
from adapters.cbe.adapter import CBEAdapter
from http_clients.http_client import FileHttpClient

# Use fixture files during development
adapter = CBEAdapter(http_client=FileHttpClient(fixtures_dir="fixtures"))

# Fetch from fixture instead of live API
result = adapter.fetch_and_parse()

# Work with result without network dependency
for record in result.records:
    print(f"{record.source_currency_code}: {record.buying_rate}")
```

---

### Dependency Injection Patterns

#### Pattern 1: Constructor Injection (Recommended)

```python
class MyBankAdapter(JSONAdapter):
    def __init__(self, http_client: HttpClient = None):
        self.http_client = http_client or RequestsHttpClient()
    
    def fetch_and_parse(self) -> ParseResult:
        response = self.http_client.fetch(self.get_source_url())
        # ... parse response
```

**Benefits**:
- Easy to test (inject MockHttpClient)
- Flexible (inject any HttpClient implementation)
- Default production behavior (RequestsHttpClient)

#### Pattern 2: Module-Level Default

```python
# adapters/mybank/adapter.py

from http_clients.http_client import RequestsHttpClient

_default_http_client = RequestsHttpClient()

class MyBankAdapter(JSONAdapter):
    def __init__(self, http_client: HttpClient = None):
        self.http_client = http_client or _default_http_client
```

**Benefits**:
- Shared client instance across adapter instances
- Connection pooling (requests sessions)

#### Pattern 3: Factory Function

```python
def create_adapter(mode: str = "production") -> MyBankAdapter:
    if mode == "production":
        return MyBankAdapter(http_client=RequestsHttpClient())
    elif mode == "test":
        return MyBankAdapter(http_client=MockHttpClient({...}))
    elif mode == "development":
        return MyBankAdapter(http_client=FileHttpClient())
    else:
        raise ValueError(f"Unknown mode: {mode}")
```

**Benefits**:
- Environment-specific configuration
- Easy mode switching

#### Pattern 4: Backward Compatibility Wrapper

For adapters that need module-level functions:

```python
_adapter = MyBankAdapter()

def parse(raw_content: str, **kwargs):
    """Backward-compatible parse function."""
    return _adapter.parse(raw_content, **kwargs).records

def fetch_and_parse(**kwargs) -> list:
    """New fetch-and-parse function using HTTP client."""
    result = _adapter.fetch_and_parse(**kwargs)
    if result.errors:
        raise ValueError(result.errors[0])
    return result.records
```

---

### Best Practices

#### 1. Always Check `is_success()` Before Using Content

```python
response = self.http_client.fetch(url)

# Good
if response.is_success():
    data = response.content
else:
    result.add_error(f"Fetch failed: {response.error}")
    return result

# Bad - content may be empty
data = response.content
```

#### 2. Use Appropriate Timeouts

```python
# API endpoints - shorter timeout
api_client = RequestsHttpClient(timeout=10.0)

# Large HTML pages - longer timeout
html_client = RequestsHttpClient(timeout=30.0)
```

#### 3. Configure Retries Based on Source Reliability

```python
# Reliable API - fewer retries
reliable_client = RequestsHttpClient(max_retries=1)

# Unreliable source - more retries with longer delay
unreliable_client = RequestsHttpClient(max_retries=3, retry_delay=5.0)
```

#### 4. Inject MockHttpClient in Tests

```python
def test_adapter_handles_network_error():
    # Mock returns error
    mock_http = MockHttpClient()
    
    adapter = MyBankAdapter(http_client=mock_http)
    result = adapter.fetch_and_parse()
    
    assert not result.is_success()
```

#### 5. Use FileHttpClient for Offline Development

```python
# In scheduler/runner.py during development
if os.getenv("OFFLINE_MODE") == "true":
    http_client = FileHttpClient(fixtures_dir="fixtures")
else:
    http_client = RequestsHttpClient()

adapter = create_adapter(http_client=http_client)
```

---

### Complete Example: Adapter with HTTP Client

```python
# adapters/mybank/adapter.py

from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord
from http_clients.http_client import HttpClient, RequestsHttpClient

class MyBankAdapter(JSONAdapter):
    """
    Adapter for MyBank JSON API.
    
    Source: https://mybank.com/api/exchange-rates
    """
    
    def __init__(self, http_client: HttpClient = None):
        self.http_client = http_client or RequestsHttpClient(
            timeout=20.0,
            max_retries=2
        )
    
    def get_source_url(self) -> str:
        return "https://mybank.com/api/exchange-rates"
    
    def get_adapter_key(self) -> str:
        return "mybank_api"
    
    def fetch_and_parse(self) -> ParseResult:
        """Fetch data from source and parse into records."""
        response = self.http_client.fetch(self.get_source_url())
        
        if not response.is_success():
            result = ParseResult()
            result.add_error(f"HTTP fetch failed: {response.error}")
            return result
        
        return self.parse(response.content)
    
    def _process_data(self, data, **kwargs) -> ParseResult:
        """Extract records from JSON data."""
        result = ParseResult()
        
        for item in data.get("rates", []):
            record = AdapterRecord(
                source_currency_code=item["currency"],
                category=item.get("category", "transactional"),
                buying_rate=self._safe_rate(item.get("buying")),
                selling_rate=self._safe_rate(item.get("selling")),
                effective_date=self._parse_iso_date(item.get("date")),
                effective_date_basis="source_published",
                source_record_key=f"{item['currency']}:{item.get('date')}",
                raw_excerpt=str(item),
                mapping_notes=None
            )
            result.records.append(record)
        
        return result


# Backward compatibility wrappers
_adapter = MyBankAdapter()

def parse(raw_content: str, **kwargs):
    result = _adapter.parse(raw_content, **kwargs)
    if result.errors:
        raise ValueError(result.errors[0])
    return result.records

def fetch_and_parse(**kwargs):
    """Fetch from source and parse."""
    result = _adapter.fetch_and_parse(**kwargs)
    if result.errors:
        raise ValueError(result.errors[0])
    return result.records
```

#### Test for the Adapter

```python
# tests/test_mybank_adapter.py

from adapters.mybank.adapter import MyBankAdapter
from http_clients.http_client import MockHttpClient
from decimal import Decimal

def test_mybank_fetch_and_parse_success():
    mock_http = MockHttpClient({
        "mybank.com": '''{
            "rates": [
                {"currency": "USD", "category": "cash", "buying": 100.0, "selling": 102.0, "date": "2024-01-15"},
                {"currency": "EUR", "category": "transactional", "buying": 110.0, "selling": 112.0, "date": "2024-01-15"}
            ]
        }'''
    })
    
    adapter = MyBankAdapter(http_client=mock_http)
    result = adapter.fetch_and_parse()
    
    assert result.is_success()
    assert len(result.records) == 2
    
    usd = result.records[0]
    assert usd.source_currency_code == "USD"
    assert usd.category == "cash"
    assert usd.buying_rate == Decimal("100.0")
    
def test_mybank_fetch_error_handling():
    # Empty mock returns 404
    mock_http = MockHttpClient()
    
    adapter = MyBankAdapter(http_client=mock_http)
    result = adapter.fetch_and_parse()
    
    assert not result.is_success()
    assert len(result.errors) > 0
    assert "HTTP fetch failed" in result.errors[0]
```

---

## Backward Compatibility

**Critical**: All existing code expects module-level functions, not classes.

### Required Wrappers

Every adapter must provide module-level wrappers:

```python
# At bottom of adapter file

_adapter = MyBankAdapter()

def parse(raw_content: str, **kwargs):
    """Backward-compatible wrapper."""
    result = _adapter.parse(raw_content, **kwargs)
    
    # Option 1: Raise on error (for adapters that historically raised)
    if result.errors:
        raise ValueError(f"MyBank: {result.errors[0]}")
    return result.records
    
    # Option 2: Return tuple (for adapters that historically returned (records, errors))
    # return result.records, result.errors

def schema_fingerprint(raw_content: str) -> str:
    return _adapter.schema_fingerprint(raw_content)
```

### Determining Return Style

Check existing tests:
- If tests expect `records = parse(raw)` → raise on error
- If tests expect `records, errors = parse(raw)` → return tuple

---

## Testing Your Adapter

### 1. Create Fixtures

```
fixtures/mybank/
├── normal.json          # Typical response
├── empty.json           # Empty rates
├── malformed.json       # Invalid format
└── unknown_currency.json
```

### 2. Write Tests

```python
# tests/test_mybank_adapter.py

from adapters.mybank.adapter import parse as mybank_parse, ADAPTER_KEY
from pathlib import Path

FIXTURE_DIR = Path("fixtures")

def _load(name: str, ext: str = "json") -> str:
    return (FIXTURE_DIR / "mybank" / f"{name}.{ext}").read_text()

def test_mybank_adapter_key():
    assert ADAPTER_KEY == "mybank_api"

def test_mybank_normal_returns_list():
    records = mybank_parse(_load("normal"))
    assert isinstance(records, list)
    assert len(records) > 0

def test_mybank_normal_usd_values():
    records = mybank_parse(_load("normal"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    assert usd.buying_rate == Decimal("161.72")
    assert usd.selling_rate == Decimal("164.95")

def test_mybank_normal_category():
    records = mybank_parse(_load("normal"))
    for r in records:
        assert r.category in ["cash", "transactional", "weighted_average", "UNKNOWN"]

def test_mybank_empty_returns_empty_list():
    records = mybank_parse(_load("empty"))
    assert records == []

def test_mybank_malformed_raises():
    with pytest.raises(ValueError):
        mybank_parse(_load("malformed"))
```

### 3. Run Tests

```bash
python3 -m pytest tests/test_mybank_adapter.py -v
```

---

## Common Patterns

### Pattern 1: Multiple Records per Currency

Many sources emit multiple categories per currency:

```python
def _process_data(self, data, **kwargs) -> ParseResult:
    result = ParseResult()
    
    for item in data["rates"]:
        currency = item["currency"]
        
        # Cash record
        if item.get("cash_buying") or item.get("cash_selling"):
            result.records.append(AdapterRecord(
                source_currency_code=currency,
                category="cash",
                buying_rate=self._safe_rate(item["cash_buying"]),
                selling_rate=self._safe_rate(item["cash_selling"]),
                # ...
            ))
        
        # Transactional record
        if item.get("txn_buying") or item.get("txn_selling"):
            result.records.append(AdapterRecord(
                source_currency_code=currency,
                category="transactional",
                buying_rate=self._safe_rate(item["txn_buying"]),
                selling_rate=self._safe_rate(item["txn_selling"]),
                # ...
            ))
    
    return result
```

### Pattern 2: Handling "No Trade" / NULL / Zero

All sentinels should normalize to `None`:

```python
def _safe_parse_rate(self, raw) -> Optional[Decimal]:
    """Handle various sentinel values."""
    if not raw:
        return None
    
    text = str(raw).strip().upper()
    
    # Check sentinels
    if text in ("", "-", "NO TRADE", "N/A", "..."):
        return None
    
    # Check for zero (some sources use 0 to mean "not offered")
    try:
        value = self._safe_rate(raw)
        if value == Decimal("0"):
            return None
        return value
    except:
        return None
```

### Pattern 3: Date Extraction from Text

```python
import re
from datetime import datetime

def _extract_date(self, text: str) -> Optional[date]:
    """Extract date from various text formats."""
    patterns = [
        (r'(\d{4}-\d{2}-\d{2})', "%Y-%m-%d"),
        (r'(\d{1,2}/\d{1,2}/\d{4})', "%d/%m/%Y"),
        (r'(\w+ \d{1,2},? \d{4})', "%B %d, %Y"),
    ]
    
    for pattern, fmt in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return datetime.strptime(match.group(1), fmt).date()
            except ValueError:
                continue
    
    return None
```

### Pattern 4: Error Accumulation

```python
def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
    result = ParseResult()
    
    for idx, table in enumerate(tables):
        try:
            # Process table
            records = self._parse_single_table(table)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_{idx}:{exc}")
            # Continue processing other tables
    
    return result
```

### Pattern 5: Custom Fingerprinting

Override `schema_fingerprint()` for source-specific structural signatures:

```python
def schema_fingerprint(self, raw_content: str) -> str:
    """Hash specific structural elements."""
    try:
        data = json.loads(raw_content)
        
        # Hash: top-level keys + first item keys
        top_keys = sorted(data.keys())
        item_keys = sorted(data["rates"][0].keys()) if data.get("rates") else []
        
        signature = {"top": top_keys, "item": item_keys}
        payload = json.dumps(signature, separators=(",", ":"))
        
        return hashlib.sha256(payload.encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"mybank:unparseable").hexdigest()
```

---

## Troubleshooting

### Issue: Tests Expect Tuple but I'm Raising Errors

**Solution**: Change wrapper to return tuple:

```python
def parse(raw_content: str):
    result = _adapter.parse(raw_content)
    return result.records, result.errors  # Return tuple, don't raise
```

### Issue: Base Class Method Doesn't Fit My Needs

**Solution**: Override the method:

```python
class MyAdapter(JSONAdapter):
    def schema_fingerprint(self, raw_content: str) -> str:
        """Custom fingerprinting instead of default."""
        # Your implementation
        pass
```

### Issue: Need Category Parameter (Type F/G adapters)

**Solution**: Override `requires_category()` and extract from `**options`:

```python
def requires_category(self) -> bool:
    return True

def _extract_from_text(self, text: str, soup: BeautifulSoup, **kwargs) -> ParseResult:
    category = kwargs.get("category", "UNKNOWN")
    # Use category in record creation
```

### Issue: Adapter Returns Empty Records

**Debug checklist**:
1. Print raw_content length - is fetch working?
2. Check if tables/data structure matches expectations
3. Add debug prints in extraction loop
4. Verify sentinels aren't filtering out all records
5. Check regex patterns with online regex tester

### Issue: Schema Fingerprint Changing on Every Fetch

**Cause**: Fingerprinting values instead of structure.

**Solution**: Only hash structural elements (keys, table count, headers), not data values:

```python
# BAD: Hashes values
hashlib.sha256(json.dumps(data).encode()).hexdigest()

# GOOD: Hashes structure
keys = sorted(data.keys())
hashlib.sha256(json.dumps(keys).encode()).hexdigest()
```

---

## Checklist for New Adapters

- [ ] Choose appropriate base class
- [ ] Implement required methods
- [ ] Add backward compatibility wrappers
- [ ] Create fixture files (normal, empty, malformed)
- [ ] Write tests (adapter key, normal parse, edge cases)
- [ ] Run tests and verify all pass
- [ ] Verify schema fingerprint is deterministic
- [ ] Test with real data (manual fetch)
- [ ] Document any special cases in adapter docstring
- [ ] Register in `infrastructure/adapter_registry.py`

---

## Additional Resources

- **ADR-006**: Source taxonomy and adapter families
- **ADR-010**: Adapter base classes design decision
- **Base classes implementation**: `adapters/base.py`
- **Example adapters**: `adapters/cbe/`, `adapters/dashen/`, `adapters/ahadu/`
- **Test examples**: `tests/test_m5_cbe_adapter.py`, `tests/test_m6_dashen_adapter.py`

---

**Questions?** Check existing adapters for patterns, or refer to ADR-006 for source classification guidance.
