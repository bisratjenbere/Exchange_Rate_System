# Exchange Rate System - Troubleshooting Guide

## Quick Diagnosis

### 1. Check Overall System Status
```bash
# View latest GitHub Actions run
# https://github.com/bisratjenbere/Exchange_Rate_System/actions

# Check which banks succeeded/failed
python -m scheduler.run_job --dry-run
```

### 2. Diagnose Specific Bank
```bash
# Run diagnostic tool
python tools/diagnose_adapter.py boa_html
python tools/diagnose_adapter.py hibret_html
python tools/diagnose_adapter.py amhara_html
```

### 3. Test Adapter Locally
```bash
# Import and test manually
python3 << 'EOF'
from adapters.banks.boa import ADAPTER, SPEC
from adapters.core.contract import ParseContext
from adapters.core.dates import business_date_now
import requests

# Fetch HTML
response = requests.get(SPEC.url)
html = response.text

# Parse
ctx = ParseContext("cash", business_date_now(), source_id=0)
result = ADAPTER.parse(html, ctx)

print(f"Records: {len(result.records)}")
print(f"Issues: {len(result.issues)}")
for record in result.records[:3]:
    print(f"  {record.source_currency_code}: {record.buying_rate}/{record.selling_rate}")
EOF
```

---

## Common Issues

### Issue: "Returns 0 records"

**Symptoms:**
- Adapter runs without errors
- But `len(result.records) == 0`
- Fallback mechanism triggered

**Causes:**
1. Table headers changed
2. Table structure changed (nested tables, div-based layout)
3. Site moved to JavaScript rendering
4. URL changed

**Solution:**
```bash
# 1. Run diagnostic
python tools/diagnose_adapter.py <bank>

# 2. Visit site in browser, inspect HTML
# 3. Update TableSpec headers
# Example:
headers={
    "currency": ("currency", "curr code", "code"),  # Add more variants
    "buy": ("buying", "buy rate", "purchase"),
    "sell": ("selling", "sell rate"),
}
```

---

### Issue: "Cloudflare protection detected"

**Symptoms:**
```
RuntimeError: HTTP fetch failed: Cloudflare protection detected
```

**Cause:**
Bank uses Cloudflare bot protection

**Solution:**
```bash
# Option 1: Install cloudscraper
pip install cloudscraper

# Option 2: Install playwright (better)
pip install playwright
playwright install chromium

# System will auto-detect and use them
```

---

### Issue: "UnboundLocalError: exc"

**Status:** ✅ FIXED in commit 4dc3ea1

**Previous Error:**
```python
UnboundLocalError: cannot access local variable 'exc' where it is not associated with a value
```

**Fix Applied:**
Added `last_exc` variable in `http_clients/http_client.py`

---

### Issue: "AddisFortuneAdapter.parse() missing ctx"

**Status:** ✅ FIXED in commit 4dc3ea1

**Previous Error:**
```python
TypeError: AddisFortuneAdapter.parse() missing 1 required positional argument: 'ctx'
```

**Fix Applied:**
Added ParseContext in `infrastructure/fallback_policy.py`

---

### Issue: "ModuleNotFoundError: No module named 'pytz'"

**Status:** ✅ FIXED in commit e843d0a

**Previous Error:**
```
ModuleNotFoundError: No module named 'pytz'
```

**Fix Applied:**
Added `pytz==2024.1` to requirements.txt

---

## Maintenance Checklist

### Weekly
- [ ] Check GitHub Actions cron job status
- [ ] Review failed banks (if any)
- [ ] Check for Cloudflare issues

### Monthly
- [ ] Run diagnostic on all banks
- [ ] Update adapters if structure changed
- [ ] Review success rate trends

### Quarterly
- [ ] Update dependencies (requirements.txt)
- [ ] Review and update header variants
- [ ] Check for new Cloudflare deployments

---

## Adapter Update Workflow

### Step 1: Identify Issue
```bash
python tools/diagnose_adapter.py <bank_name>
```

### Step 2: Inspect Website
1. Open bank URL in browser
2. Open DevTools (F12)
3. Find the exchange rate table
4. Inspect table headers
5. Note exact header text

### Step 3: Update TableSpec
```python
# adapters/banks/<bank>.py

SPEC = TableSpec(
    key="<bank>_html",
    url="https://...",
    headers={
        # Add actual header text from step 2
        "currency": ("currency", "curr", "code", "<actual header>"),
        "buy": ("buying", "buy", "<actual header>"),
        "sell": ("selling", "sell", "<actual header>"),
    },
    required=("currency", "buy", "sell"),
)
```

### Step 4: Test
```bash
# Run adapter test
python -m pytest tests/migration/test_<bank>_new.py -v

# Or test manually
python3 << EOF
from adapters.banks.<bank> import ADAPTER, SPEC
# ... test code from above ...
EOF
```

### Step 5: Commit
```bash
git add adapters/banks/<bank>.py
git commit -m "fix: update <bank> adapter for new table structure"
git push origin main
```

---

## Debug Mode

### Enable Verbose Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Inspect Parsed HTML
```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, 'lxml')
tables = soup.find_all('table')

for idx, table in enumerate(tables):
    print(f"Table {idx}:")
    headers = table.find('tr').find_all(['th', 'td'])
    print([h.get_text(strip=True) for h in headers])
```

### Check API Endpoints (if available)
```python
import requests

# Some banks have JSON APIs
response = requests.get("https://bank.com/api/rates")
data = response.json()
print(data)
```

---

## Getting Help

1. **Check Documentation**
   - `README.md` - Project overview
   - `ADAPTER_RESILIENCE.md` - Resilience patterns
   - This file - Troubleshooting

2. **Run Diagnostics**
   ```bash
   python tools/diagnose_adapter.py <bank>
   ```

3. **Check Recent Changes**
   ```bash
   git log --oneline -10
   git show <commit-hash>
   ```

4. **Review GitHub Actions**
   - https://github.com/bisratjenbere/Exchange_Rate_System/actions
   - Check error logs
   - Look for patterns

---

## Performance Tips

### Parallel Collection
Already optimized with workload balancer:
- Browser adapters: Lower priority
- API adapters: Higher priority
- Automatic worker calculation

### Connection Pooling
Already implemented:
- Database: ThreadedConnectionPool (2-10 connections)
- HTTP: Reusable sessions

### Retry Strategy
Already configured:
- Max retries: 3
- Exponential backoff
- Cloudflare detection

---

## Security Notes

### SQL Injection
✅ Fixed - Using parameterized queries and sql.Identifier()

### Environment Variables
Sensitive data in environment:
- `DATABASE_URL` - Neon database connection
- `ALLOWED_ORIGINS` - CORS configuration

### Rate Limiting
Built-in delay between requests to avoid bans

---

## Useful Commands

```bash
# Full cron job locally
python -m scheduler.run_job

# Dry run (no database writes)
python -m scheduler.run_job --dry-run

# Single bank
python -m scheduler.cli run <bank_name>

# Health check
python -m scheduler.health

# View metrics
curl http://localhost:5000/metrics
```
