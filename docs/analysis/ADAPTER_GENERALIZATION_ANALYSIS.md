# Adapter Generalization Analysis
## Should We Have 21 Adapters or Can We Generalize?

**Question**: Why 21 separate adapters? Can we use configuration/templates instead?

**TL;DR**: Current approach (21 adapters) is **correct for this domain**. Attempted generalization would create **more complexity**, not less.

---

## Table of Contents
1. [The Generalization Temptation](#the-temptation)
2. [Reality Check: Bank Data Variance](#reality-check)
3. [Cost-Benefit Analysis](#cost-benefit)
4. [What CAN Be Generalized](#what-can-be-generalized)
5. [Senior Engineer Decision](#decision)

---

## The Generalization Temptation

### Junior Thinking:
> "21 adapters is a lot of code duplication. Can't we just use configuration?"

```yaml
# dream.yml - "One config to rule them all"
banks:
  - name: CBE
    url: https://combanketh.et/api
    format: json
    fields:
      currency: currency.CurrencyCode
      buying: cashBuying
      selling: cashSelling
  
  - name: DBE  
    url: https://dbe.com.et/
    format: html
    selector: table.rates
    fields:
      currency: td[1]
      buying: td[2]
      selling: td[3]
```

**Seems attractive**:
- ✅ One adapter, many configs
- ✅ No code duplication
- ✅ Easy to add banks (just YAML)

**But is this real?** Let's check...

---

## Reality Check: Bank Data Variance

### Let's Look at Actual Bank Data

#### **Type A: CBE (Ideal Case)**
```json
{
  "id": "507f1f77bcf86cd799439011",
  "Date": "2026-10-13",
  "ExchangeRate": [{
    "id": "507f191e810c19729de860ea",
    "currency": {"CurrencyCode": "USD", "CurrencyName": "US Dollar"},
    "cashBuying": 160.2319,
    "cashSelling": 161.9506,
    "transactionalBuying": 160.2319,
    "transactionalSelling": 161.9506
  }]
}
```

**Characteristics**:
- ✅ Stable IDs (MongoDB ObjectIDs)
- ✅ Clear date field
- ✅ Categories explicitly labeled
- ✅ Two rate pairs per currency
- ✅ Nested structure

---

#### **Type B1: Rammis**
```json
{
  "base_currency": "ETB",
  "effective_date": "2026-10-13",
  "rates": [{
    "id": 42,
    "currency": "USD",
    "effective_date": "2026-10-13",  // ← Per-row date (different!)
    "buying": "160.23",
    "selling": "161.95",
    "created_at": "2026-10-13T08:15:32Z"
  }]
}
```

**Differences from CBE**:
- ❌ Different nesting (envelope vs array)
- ❌ Date at TWO levels (envelope + per-row)
- ❌ Single rate pair (no categories)
- ❌ Integer IDs, not ObjectIDs
- ❌ Rates as strings, not numbers

---

#### **Type F: DBE (HTML)**
```html
<span class="tablepress-table-description">
  Exchange Rates for October 13, 2026
</span>
<table>
  <tr><th>Currency</th><th>Code</th><th>Buying</th><th>Selling</th></tr>
  <tr><td>US Dollar</td><td>USD</td><td>160.23</td><td>161.95</td></tr>
</table>
```

**Differences**:
- ❌ HTML, not JSON
- ❌ Date in prose text, not structured field
- ❌ Date format: "October 13, 2026" (needs parsing)
- ❌ Single table, no category
- ❌ No IDs at all

---

#### **Type G: Ahadu (Text Extraction)**
```html
<p>EXCHANGE RATE FOR : 13/10/2026</p>
<p>CURR : USD Buying Rate : 160.23 Selling Rate : 161.95</p>
<p>CURR : EUR Buying Rate : No Trade Selling Rate : 175.50</p>
```

**Differences**:
- ❌ No structure (plain text)
- ❌ Regex extraction needed
- ❌ Date format: DD/MM/YYYY
- ❌ "No Trade" as string sentinel
- ❌ No tables, no JSON, just text

---

#### **Type B2: ADIB (Flat Array)**
```json
[
  {
    "id": 2,
    "currency": "USD",
    "buying": "0.0000",  // ← Zero means not offered
    "selling": "0.0000",
    "transactionBuying": "160.2319",
    "transactionSelling": "161.9506",
    "weightedBuying": "160.1234",
    "weightedSelling": "161.8765",
    "updatedAt": "2026-10-13T08:15:32.000Z"  // ← Timestamp, not date
  },
  {"id": 1, "currency": "ETB", ...}  // ← Must skip quote currency row
]
```

**Differences**:
- ❌ Flat array (no envelope)
- ❌ SIX rate fields per currency
- ❌ Must skip ETB row (quote currency)
- ❌ Zero = "not offered" (not NULL)
- ❌ Timestamp needs date extraction
- ❌ updatedAt per currency (not single date)

---

### **Can Configuration Handle This?**

Let's try...

```yaml
# attempt.yml
cbe:
  format: json
  date_path: Date
  date_format: iso
  records_path: ExchangeRate
  categories:
    - name: cash
      buying: cashBuying
      selling: cashSelling
    - name: transactional
      buying: transactionalBuying
      selling: transactionalSelling

rammis:
  format: json
  date_path: rates[0].effective_date  # ← Use per-row date
  date_format: iso
  records_path: rates
  categories:
    - name: UNKNOWN  # ← No category info
      buying: buying
      selling: selling

dbe:
  format: html
  date_extraction: regex  # ← Different parsing!
  date_pattern: "(\w+)\s+(\d+),\s+(\d{4})"  # ← Complex regex
  date_format: prose  # ← Needs month name lookup
  records_path: table tr[td]
  categories:
    - name: UNKNOWN
      buying: td[2]
      selling: td[3]

ahadu:
  format: text  # ← Not even HTML structure
  date_extraction: regex
  date_pattern: "(\d{1,2})/(\d{1,2})/(\d{4})"
  date_format: dmy
  records_extraction: regex  # ← Completely different!
  records_pattern: "CURR\s*:\s*([A-Z]{3}).*Buying Rate\s*:\s*([\d.]+|No Trade)"
  # ... this is getting ugly
```

**Problems**:
1. ❌ Configuration is now **code in YAML**
2. ❌ Need different parsers for each format
3. ❌ Complex logic (skip ETB row, per-row dates, "No Trade" handling)
4. ❌ YAML becomes harder to maintain than Python
5. ❌ Debugging: which YAML key caused the issue?

---

## Cost-Benefit Analysis

### **Option 1: Current (21 Adapters)**

**Costs**:
- 21 files (~150 lines each = 3,150 lines)
- Some code duplication (parse loops, safe_rate helpers)

**Benefits**:
- ✅ Each adapter is **self-contained** (all logic in one place)
- ✅ Easy to debug (one adapter = one file)
- ✅ Easy to test (one fixture per adapter)
- ✅ Easy to understand (Python, not YAML DSL)
- ✅ Bank-specific logic explicit (skip ETB, handle "No Trade")
- ✅ Type-safe (IDE autocomplete, type checking)
- ✅ Flexible (can handle ANY bank format)

---

### **Option 2: Generic Adapter + Configuration**

**Costs**:
- Need interpreter for YAML DSL
- Need different parsers (JSON, HTML, text extraction)
- Need expression evaluator (JSONPath, XPath, regex)
- Need conditional logic in config (if this, skip that)
- Config becomes programming language
- Debugging harder (logic spread across code + config)
- Testing harder (need to test interpreter + configs)

**Benefits**:
- ✅ Fewer Python files
- ⚠️ **But more total complexity** (code + config + interpreter)

---

### **Real World Example: Web Scraping Tools**

**Scrapy** (Python framework) tried this:
- Started with "config-driven" scraping
- Reality: Complex sites need custom code
- Result: Hybrid (simple config + custom spiders for complex sites)

**Conclusion**: For diverse data sources, **code beats configuration**.

---

## What CAN Be Generalized

### ✅ **Shared Utilities** (Already Done)

```python
# pipeline/normalize.py - SHARED by all adapters
def normalize_rate(raw) -> Optional[Decimal]:
    # All adapters use this
    
def normalize_currency_code(raw) -> Optional[str]:
    # All adapters use this
```

**Good generalization**: Common transformation logic

---

### ✅ **Base Class with Common Behavior** (Proposed)

```python
class BankAdapter(ABC):
    """All adapters inherit common behaviors."""
    
    @abstractmethod
    def parse(self, content: str) -> ParseResult:
        pass  # Must implement
    
    # Common utilities available to all
    def _safe_rate(self, raw) -> Optional[Decimal]:
        try:
            return normalize_rate(raw)
        except ValueError:
            return None
    
    def _parse_iso_date(self, date_str: str) -> Optional[date]:
        try:
            return date.fromisoformat(date_str.strip())
        except (ValueError, AttributeError):
            return None
```

**Good generalization**: Common helper methods

---

### ✅ **Adapter Type Hierarchy** (Could Add)

```python
class JSONAdapter(BankAdapter):
    """Base for JSON-based adapters."""
    
    def parse(self, content: str) -> ParseResult:
        data = self._parse_json(content)
        return self._process_data(data)
    
    def _parse_json(self, content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parse error: {e}")
    
    @abstractmethod
    def _process_data(self, data: dict) -> ParseResult:
        pass  # Subclass implements bank-specific logic


class HTMLTableAdapter(BankAdapter):
    """Base for HTML table-based adapters."""
    
    def parse(self, content: str) -> ParseResult:
        soup = BeautifulSoup(content, "html.parser")
        tables = soup.find_all("table")
        return self._process_tables(tables)
    
    @abstractmethod
    def _process_tables(self, tables) -> ParseResult:
        pass


# Now adapters can be shorter:
class CBEAdapter(JSONAdapter):
    def _process_data(self, data: dict) -> ParseResult:
        # Bank-specific logic only
        records = []
        for pub in data:
            # ... CBE-specific extraction ...
        return ParseResult(records=records)
```

**Good generalization**: Common parsing infrastructure

---

### ❌ **Template-Based Generation** (BAD IDEA)

```yaml
# DON'T DO THIS
banks:
  cbe:
    format: json
    schema:
      date: "{{root.Date}}"
      records: "{{root.ExchangeRate}}"
      fields:
        currency: "{{record.currency.CurrencyCode}}"
        buying: "{{record.cashBuying}}"
```

**Why bad**:
- ❌ Not expressive enough for complex logic
- ❌ Becomes a programming language
- ❌ Hard to debug
- ❌ Hard to test

---

## Senior Engineer Decision

### **The Right Approach: Layered Abstraction**

```
Layer 1: Common Utilities (normalize_rate, parse_date)
         ↑
Layer 2: Type-Specific Base Classes (JSONAdapter, HTMLAdapter)
         ↑
Layer 3: Bank-Specific Adapters (CBEAdapter, DBEAdapter)
         ↑
Layer 4: Adapter Factory (create_adapter("cbe_api"))
```

**Each layer adds value**:
- Layer 1: DRY for transformations
- Layer 2: DRY for format parsing
- Layer 3: Bank-specific extraction logic
- Layer 4: Uniform creation interface

---

### **Why 21 Adapters is CORRECT**

#### **1. Domain Complexity**

Banks are **independent entities** with no coordination:
- No standard format
- No shared API contract
- Each bank designed their own system
- Formats change independently

**Analogy**: Like parsing 21 different file formats (CSV, JSON, XML, etc.)
- You wouldn't try to generalize with one config
- You'd write a parser for each format

---

#### **2. Explicit > Implicit**

```python
# GOOD: Explicit (current)
if row.get("id") == ETB_ROW_ID:
    return []  # Skip quote currency

# BAD: Configuration magic
skip_if:
  - field: id
    equals: 1
    reason: quote_currency
```

**Explicit code**:
- ✅ Clear what's happening
- ✅ Easy to debug
- ✅ Type-safe
- ✅ IDE support

---

#### **3. Test Independence**

```python
# Current: Test one adapter
def test_cbe_adapter():
    adapter = CBEAdapter()
    result = adapter.parse(fixture)
    assert len(result.records) == 32

# With config: Test interpreter + config
def test_config_adapter():
    adapter = ConfigurableAdapter(config_cbe)
    result = adapter.parse(fixture)
    # If it fails, is bug in:
    # - Interpreter?
    # - Config syntax?
    # - Bank data?
    # Harder to isolate!
```

---

#### **4. Change Frequency**

**Reality**: Banks change formats ~1-2 times per year
- Low change frequency
- When change happens, need custom logic anyway
- Config wouldn't save time

**If** banks changed weekly → config might help
**But** they don't → code is simpler

---

## Comparison Table

| Aspect | 21 Adapters | Generic + Config |
|--------|-------------|------------------|
| **Lines of code** | 3,150 lines Python | 1,000 lines Python + 1,500 lines YAML + 500 lines interpreter |
| **Complexity** | Low (straightforward code) | High (DSL + interpreter) |
| **Debuggability** | High (stack traces, IDE) | Low (YAML errors cryptic) |
| **Testability** | High (one test per adapter) | Medium (test interpreter + configs) |
| **Flexibility** | High (any logic possible) | Low (limited by DSL) |
| **Maintainability** | High (find all in one file) | Low (logic split across files) |
| **Onboarding** | Easy (Python developers) | Hard (learn DSL + interpreter) |
| **Type Safety** | Yes (mypy, IDE) | No (YAML is untyped) |
| **Change Impact** | Isolated (one adapter) | Wide (interpreter affects all) |

**Winner**: 21 Adapters

---

## Real-World Parallels

### **Similar Systems That Don't Generalize**

1. **Stripe Payment Adapters**
   - Separate adapter for each payment provider
   - Not configurable
   - Each provider has unique quirks

2. **Database Drivers**
   - psycopg2 (PostgreSQL), pymongo (MongoDB), mysqlclient (MySQL)
   - Not generalized
   - Each database too different

3. **Language Parsers**
   - Separate parser for Python, Java, JavaScript
   - Not configurable
   - Grammar too different

**Pattern**: When sources are **fundamentally different**, separate implementations win.

---

## What About Adding New Banks?

### **Current Process** (with 21 adapters):

```bash
# 1. Copy template (5 minutes)
cp -r adapters/template/ adapters/newbank/

# 2. Implement parse() (30-60 minutes)
# - Look at bank's actual response
# - Write extraction logic
# - Handle edge cases

# 3. Write tests (30 minutes)
# - Add fixture
# - Test normal + edge cases

# 4. Register (5 minutes)
@register_adapter("newbank_api")
class NewBankAdapter(JSONAdapter):
    # ...

# Total: 1-2 hours
```

---

### **With Generic Adapter** (theoretical):

```bash
# 1. Write YAML config (60 minutes)
# - Figure out config syntax
# - Try to express complex logic in YAML
# - Discover config can't express needed logic
# - File bug against interpreter

# 2. Wait for interpreter enhancement (days/weeks)

# 3. Update config again (30 minutes)

# 4. Debug why it doesn't work (60 minutes)
# - YAML syntax error? Interpreter bug? Bank data changed?
# - Hard to tell

# Total: 2-3 hours + waiting
```

**No time savings** + more frustration

---

## Recommended Architecture

### **Current Approach + Minor Improvements**

```python
# Layer 1: Shared utilities (already exists)
pipeline/normalize.py

# Layer 2: Type-specific base classes (NEW)
class JSONAdapter(BankAdapter):
    def parse(self, content: str):
        data = self._parse_json(content)
        return self._process_data(data)
    
    @abstractmethod
    def _process_data(self, data) -> ParseResult:
        pass

class HTMLTableAdapter(BankAdapter):
    def parse(self, content: str):
        soup = self._parse_html(content)
        return self._process_html(soup)
    
    @abstractmethod
    def _process_html(self, soup) -> ParseResult:
        pass

# Layer 3: Bank adapters (already exists, now shorter)
class CBEAdapter(JSONAdapter):
    def _process_data(self, data):
        # Only bank-specific logic
        records = []
        for pub in data:
            records.extend(self._parse_publication(pub))
        return ParseResult(records=records)

class DBEAdapter(HTMLTableAdapter):
    def _process_html(self, soup):
        # Only bank-specific logic
        tables = soup.find_all("table")
        return ParseResult(records=self._parse_table(tables[0]))
```

**Benefits**:
- ✅ Reduces duplication (JSON parsing, HTML parsing)
- ✅ Keeps bank logic explicit
- ✅ Still easy to test/debug
- ✅ Best of both worlds

---

## Final Recommendation

### **Keep 21 Adapters** ✅

**Reasons**:
1. **Domain Reality**: Banks are fundamentally different
2. **Simplicity**: Code is simpler than config + interpreter
3. **Maintainability**: Easier to debug and modify
4. **Flexibility**: Can handle any bank format
5. **Testing**: Isolated, focused tests
6. **Cost-Benefit**: Generalization adds complexity without savings

---

### **Do Add**:
- ✅ Type-specific base classes (`JSONAdapter`, `HTMLAdapter`)
- ✅ More shared utilities (date parsing helpers)
- ✅ Better factory pattern for adapter creation

### **Don't Add**:
- ❌ Generic configurable adapter
- ❌ YAML-based bank definitions
- ❌ Template engine for extraction

---

## Lessons for Seniors

### **When to Generalize**:
- ✅ Many **similar** cases (80%+ overlap)
- ✅ Changes happen **frequently**
- ✅ Generalization **reduces** complexity
- ✅ Config is **simpler** than code

### **When NOT to Generalize**:
- ❌ Cases are **fundamentally different**
- ❌ Changes are **infrequent**
- ❌ Generalization **adds** complexity
- ❌ Config becomes a **programming language**

### **This Case**:
- 32 banks, 7 format families
- Changes 1-2x per year per bank
- Differences are fundamental (JSON vs HTML vs text)
- Config would be as complex as code

**Verdict**: Don't generalize. **21 adapters is the right answer.**

---

## Quotes from Seniors

> "The first rule of abstraction is: don't abstract until you have 3 concrete examples."
> — Sandi Metz

(We have 7 format families → could abstract those)

> "Duplication is far cheaper than the wrong abstraction."
> — Sandi Metz

(21 adapters have some duplication, but it's cheaper than config DSL)

> "Make it work, make it right, make it fast."
> — Kent Beck

(21 adapters **work** and are **right**. Don't over-optimize.)

---

## Conclusion

**The 21-adapter approach is a **senior decision**, not a junior mistake.**

**Why**:
- Recognizes domain complexity (banks are different)
- Chooses simplicity (code over config)
- Optimizes for maintainability (explicit over clever)
- Values flexibility (can handle any format)
- Pragmatic (good enough, ship it)

**The junior trap** would be:
- "Let's generalize!"
- Build config system
- Spend 3 months
- Still need custom code for edge cases
- End up with **more** complexity

**The senior approach**:
- 21 adapters + shared utilities
- 2 hours to add new bank
- Simple, testable, maintainable
- Ships today

---

**Bottom Line**: Sometimes **the "naive" solution is actually the correct one**. Experience teaches when NOT to over-engineer.
