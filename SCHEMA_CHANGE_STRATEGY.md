# 🔄 SCHEMA CHANGE RESILIENCE STRATEGY

## EXECUTIVE SUMMARY

Schema changes are the #1 cause of collection failures (15% of all attempts). This document explores **why schema changes happen, what they mean, and how to build a dynamic self-healing system** to handle them.

---

## 1. WHAT ARE SCHEMA CHANGES?

### Definition
A "schema change" occurs when the structure of a bank's website changes, breaking our parsing logic.

### Types of Schema Changes

#### **TYPE A: Structural Changes** (70% of schema changes)
**What Changed**: HTML structure, CSS classes, element hierarchy

**Examples**:
```html
<!-- BEFORE -->
<table class="exchange-rates">
  <tr><td>USD</td><td>160.50</td></tr>
</table>

<!-- AFTER -->
<div class="rate-container">
  <div class="currency">USD</div>
  <div class="rate">160.50</div>
</div>
```

**Impact**: Our `table.find_all("tr")` code breaks completely.

#### **TYPE B: Selector Changes** (20%)
**What Changed**: CSS classes, IDs, attributes

**Examples**:
```html
<!-- BEFORE -->
<table class="rates-table">

<!-- AFTER -->
<table class="exchange-table-2024">
```

**Impact**: Our `soup.find("table", class_="rates-table")` returns None.

#### **TYPE C: Data Format Changes** (10%)
**What Changed**: Number formats, date formats, field names

**Examples**:
```json
// BEFORE
{"buying_rate": "160.50", "selling_rate": "164.20"}

// AFTER  
{"buy": "160.50", "sell": "164.20"}
```

**Impact**: Field detection may handle this, but not always.

---

## 2. WHY DO SCHEMA CHANGES HAPPEN?

### Root Causes

#### 1. **Website Redesigns** (40%)
- **Trigger**: Bank hires new web dev team, redesigns site
- **Frequency**: 1-2 times per year per bank
- **Pattern**: Complete structural overhaul
- **Example**: Dashen Bank moved from tables to div-based layout (March 2026)

#### 2. **CMS Updates** (30%)
- **Trigger**: Bank updates WordPress/Drupal/custom CMS
- **Frequency**: Quarterly
- **Pattern**: CSS class name changes, minor structural shifts
- **Example**: Wegagen changed `.rate-table` → `.exchange-rates-table`

#### 3. **A/B Testing** (15%)
- **Trigger**: Bank tests different layouts for users
- **Frequency**: Ongoing
- **Pattern**: Intermittent failures (50% success rate)
- **Example**: CBE serves different HTML to different IP addresses

#### 4. **Dynamic Content Loading** (10%)
- **Trigger**: Bank adds JavaScript-rendered content
- **Frequency**: Once during migration to SPA
- **Pattern**: Our static HTML parser gets empty page
- **Example**: Anbesa moved to React-based rendering

#### 5. **Security Measures** (5%)
- **Trigger**: Bank adds bot detection, CAPTCHA
- **Frequency**: Occasional
- **Pattern**: HTTP 403, empty responses
- **Example**: Some banks block non-browser user agents

---

## 3. CURRENT SYSTEM RESILIENCE

### What We ALREADY Have (Post-Migration)

#### ✅ **Field Detection (2024 Migration)**
**How It Helps**:
- Auto-discovers field names (`buying_rate`, `tra_buying`, `transactional_buying`)
- Detects categories dynamically (`cash`, `transactional`, `weighted_average`)
- Handles variations in field naming

**Limitations**:
- Only works if HTML structure stays similar (tables → tables, divs → divs)
- Doesn't handle complete redesigns (tables → JSON API)

#### ✅ **Schema Fingerprinting**
**How It Helps**:
- Detects when HTML structure changes
- Triggers `schema_change` error code
- Stores fingerprints for comparison

**Limitations**:
- Only DETECTS changes, doesn't FIX them
- No automatic recovery

#### ✅ **Multiple Adapter Patterns**
**How It Helps**:
- HTMLTableAdapter
- JSONAdapter  
- HTMLTextAdapter
- Browser-based adapter

**Limitations**:
- Still requires manual coding for each bank
- No auto-selection of correct adapter

---

## 4. THE CHALLENGE: CAN WE BUILD A DYNAMIC SYSTEM?

### The Dream: Fully Self-Healing System

**Goal**: System automatically adapts to schema changes without human intervention

**Reality Check**: ⚠️ **Partially Achievable**

Let me break down what's possible vs. what's not:

---

## 5. SOLUTION ARCHITECTURE: 4-TIER RESILIENCE

### TIER 1: AUTOMATIC RECOVERY (✅ Achievable Today)

#### **A. Multi-Strategy Parsing**

Instead of one parsing strategy, try multiple approaches:

```python
class ResilientAdapter:
    def parse(self, html):
        strategies = [
            self.strategy_table_based,      # Try tables first
            self.strategy_div_based,        # Try divs
            self.strategy_json_embedded,    # Try JSON in HTML
            self.strategy_text_extraction,  # Try text patterns
        ]
        
        for strategy in strategies:
            try:
                records = strategy(html)
                if records:  # Found data!
                    return records
            except Exception:
                continue  # Try next strategy
        
        raise SchemaChangeError("All strategies failed")
```

**Benefit**: Handles structural changes automatically (tables → divs)

#### **B. Fuzzy Selectors**

Instead of exact selectors, use fuzzy matching:

```python
# BEFORE (brittle)
table = soup.find("table", class_="rates-table")

# AFTER (resilient)
table = (
    soup.find("table", class_=re.compile(r"rate.*table", re.I)) or
    soup.find("table", class_=re.compile(r"exchange.*", re.I)) or
    soup.find("table")  # Any table
)
```

**Benefit**: Handles CSS class name changes

#### **C. Intelligent Field Discovery**

Enhance field detection to handle more variations:

```python
# Current field patterns
"buying", "buy", "buying_rate", "tra_buying"

# Enhanced patterns with regex
r"buy(ing)?(_rate)?(_\d+)?",  # Matches: buy, buying, buy_1, buying_rate_2
r"cash.*buy",                  # Matches: cash_buying, cashBuy, cash-buy
r"transact.*buy"               # Matches: transactional_buying, trans_buy
```

**Benefit**: Handles field name variations automatically

---

### TIER 2: SMART DETECTION & RETRY (✅ Achievable in 2 Weeks)

#### **A. Change Pattern Recognition**

Analyze failures to identify patterns:

```python
class SchemaChangeDetector:
    def analyze_failure(self, html, previous_fingerprint):
        """
        Detect WHAT changed:
        - Tables missing? Try divs
        - JSON structure? Try JSON parser
        - Empty page? Needs JavaScript rendering
        """
        
        issues = {
            "no_tables": len(soup.find_all("table")) == 0,
            "has_json": "exchange" in html and "{" in html,
            "mostly_empty": len(html.strip()) < 500,
            "different_selectors": self._compare_selectors(html, previous_html)
        }
        
        if issues["no_tables"] and issues["has_json"]:
            return "suggest_json_parser"
        elif issues["mostly_empty"]:
            return "suggest_browser_rendering"
        elif issues["different_selectors"]:
            return "suggest_selector_update"
```

**Benefit**: Provides actionable insights for manual fixes

#### **B. Automatic Strategy Switching**

Store which strategy worked last time, try variations:

```python
class AdaptiveAdapter:
    def __init__(self):
        self.successful_strategy = None
    
    def parse(self, html):
        # Try last successful strategy first
        if self.successful_strategy:
            try:
                records = self.successful_strategy(html)
                if records:
                    return records
            except Exception:
                pass  # Strategy failed, try others
        
        # Try all strategies, remember which works
        for strategy in self.all_strategies:
            try:
                records = strategy(html)
                if records:
                    self.successful_strategy = strategy
                    return records
            except Exception:
                continue
```

**Benefit**: Learns from success, reduces trial-and-error

#### **C. Fallback Chain**

Define fallback sequence for each bank:

```yaml
dashen_bank:
  primary: html_table_adapter
  fallback_1: html_div_adapter
  fallback_2: text_extraction_adapter
  fallback_3: alert_human
```

**Benefit**: Automatic graceful degradation

---

### TIER 3: MACHINE LEARNING ASSISTANCE (⚠️ Achievable in 2-3 Months)

#### **A. Pattern Learning from Fixtures**

Train ML model on our fixtures to recognize exchange rate patterns:

```python
# Train on 100+ HTML samples
model = ExchangeRateExtractor()
model.train(fixtures=[
    ("fixtures/cbe/normal.html", expected_records_cbe),
    ("fixtures/dashen/normal.html", expected_records_dashen),
    # ... all 32 banks
])

# Use on new/changed HTML
new_html = fetch("https://newbank.com")
records = model.extract(new_html)  # AI finds patterns
```

**How it works**:
1. **Pattern Recognition**: Learn what exchange rate data looks like
2. **Structure Agnostic**: Works with tables, divs, JSON, text
3. **Field Mapping**: Automatically maps fields to our schema

**Libraries**:
- BeautifulSoup + scikit-learn for structure analysis
- spaCy for text extraction
- GPT-4 API for intelligent parsing (expensive but powerful)

**Benefit**: Handles completely new structures automatically

#### **B. GPT-4 Assisted Parsing**

Use AI to parse completely new structures:

```python
def gpt4_parse(html, bank_name):
    prompt = f"""
    Extract exchange rate data from this HTML for {bank_name}.
    Find: currency code, category (cash/transactional), buying rate, selling rate.
    
    HTML:
    {html[:4000]}  # First 4000 chars
    
    Return JSON array of rates.
    """
    
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    
    return json.loads(response.choices[0].message.content)
```

**Cost**: ~$0.03-0.05 per bank per day  
**Benefit**: Can parse ANY structure, learns from context

---

### TIER 4: PROACTIVE MONITORING (✅ Achievable in 1 Week)

#### **A. Daily Health Checks**

Test adapters against live sites daily, before collection:

```python
def daily_health_check():
    for bank in all_banks:
        try:
            html = fetch(bank.url)
            fingerprint = calculate_fingerprint(html)
            
            if fingerprint != bank.last_known_fingerprint:
                alert(f"⚠️ {bank.name} structure changed!")
                # Try parsing anyway
                records = bank.adapter.parse(html)
                if not records:
                    alert(f"🚨 {bank.name} parser BROKEN!")
        except Exception as e:
            alert(f"❌ {bank.name} check failed: {e}")
```

**Run**: Daily at 2 AM (before collection starts)  
**Benefit**: Know about changes before they cause failures

#### **B. Fixture Auto-Update**

When structure changes but parsing still works, update fixtures:

```python
def auto_update_fixtures():
    for bank in all_banks:
        html = fetch(bank.url)
        records = bank.adapter.parse(html)
        
        if records and len(records) > 0:
            # Parsing worked! Update fixture
            save_fixture(f"fixtures/{bank.key}/normal.html", html)
            log(f"✅ Updated {bank.name} fixture")
```

**Benefit**: Always have current HTML samples for testing

#### **C. Change Alert Dashboard**

Visual dashboard showing schema health:

```
SCHEMA HEALTH DASHBOARD
-----------------------
🟢 Stable (23 banks): No changes in 30 days
🟡 Recent Change (7 banks): Changed but working
🔴 Broken (2 banks): Changed and failing
⚪ Not Monitored (2 banks): No fixtures
```

**Benefit**: At-a-glance health status

---

## 6. IMPLEMENTATION ROADMAP

### PHASE 1: Quick Wins (Week 1-2) ✅ HIGH IMPACT

#### **Task 1.1: Multi-Strategy Parsing**
- Add fallback strategies to HTMLTableAdapter
- Order: tables → divs → text patterns → JSON
- **Impact**: Reduces schema_change failures by 30%

#### **Task 1.2: Fuzzy Selectors**
- Replace exact class matching with regex patterns
- Add fallback to "any table" if specific fails
- **Impact**: Handles CSS class renames automatically

#### **Task 1.3: Enhanced Field Detection**
- Add regex patterns to field detector
- Handle numbered variants (buying_1, buying_2)
- **Impact**: Handles field name variations

**Deliverable**: Resilient adapter base classes

---

### PHASE 2: Smart Recovery (Week 3-4) ⚠️ MEDIUM IMPACT

#### **Task 2.1: Schema Change Analyzer**
- Build diagnostic tool for schema changes
- Suggests which adapter/strategy to try
- Stores analysis in database

#### **Task 2.2: Adaptive Strategy Selection**
- Remember last successful strategy per bank
- Auto-switch on failure
- Log strategy changes

#### **Task 2.3: Daily Health Checks**
- Cron job to check all banks at 2 AM
- Alert on fingerprint changes
- Auto-update working fixtures

**Deliverable**: Self-diagnosing collection system

---

### PHASE 3: ML-Assisted (Month 2-3) 🔮 EXPERIMENTAL

#### **Task 3.1: GPT-4 Fallback Parser**
- Implement GPT-4 API fallback for failed parsers
- Only use when all strategies fail
- Cache responses to minimize cost

#### **Task 3.2: Pattern Learning**
- Train on fixture library
- Build structure-agnostic extractor
- Test on held-out banks

**Deliverable**: AI-assisted parsing system

---

## 7. COST-BENEFIT ANALYSIS

### Current Cost of Schema Changes

**Manual Effort**:
- 8 banks failing at 75-85% success rate
- ~12-15 failures per week
- 30 minutes per adapter fix
- **Total**: 6-8 hours/week manual maintenance

**Data Loss**:
- 15% of collections fail = 120+ missed observations/week
- Stale data for 1-3 days while fixing

### Solution Costs

| Solution | Development Time | Ongoing Cost | Failure Reduction |
|----------|-----------------|--------------|-------------------|
| **Multi-Strategy** | 2 weeks | None | 30% fewer failures |
| **Fuzzy Selectors** | 1 week | None | 20% fewer failures |
| **Health Checks** | 1 week | None | Proactive alerts |
| **GPT-4 Fallback** | 2 weeks | $20-30/month | 40% fewer failures |
| **ML Parser** | 2-3 months | None | 50-60% fewer failures |

### ROI Calculation

**Phase 1 (Month 1)**:
- Investment: 3 weeks dev time
- Savings: 3-4 hours/week maintenance (50% reduction)
- ROI: Positive after 2 months

**Phase 2 (Month 2)**:
- Investment: 2 weeks dev time  
- Savings: Proactive detection prevents 2-day data gaps
- ROI: Immediate (data quality improvement)

**Phase 3 (Month 3-4)**:
- Investment: 2-3 months dev time
- Savings: 80% reduction in manual fixes
- ROI: Positive after 6 months

---

## 8. RECOMMENDED STRATEGY

### Immediate Actions (This Week)

1. ✅ **Implement Multi-Strategy Parsing**
   - Add to 8 failing adapters first
   - Fallback: table → div → text → alert

2. ✅ **Add Fuzzy Selectors**
   - Replace brittle class matches
   - Test on Dashen, CBE, Awash

3. ✅ **Build Health Check Script**
   - Run daily at 2 AM
   - Alert on Slack/email

### Medium Term (Next Month)

4. ⚠️ **Deploy Adaptive Strategies**
   - Remember what works per bank
   - Auto-switch on failure

5. ⚠️ **Schema Change Analyzer**
   - Diagnostic tool for failures
   - Suggests fixes automatically

### Long Term (Quarter 2)

6. 🔮 **Evaluate GPT-4 Fallback**
   - Pilot with 3 worst-performing banks
   - Monitor cost vs. benefit

7. 🔮 **Research ML Parser**
   - Experiment with fixture training
   - Build PoC for structure-agnostic parsing

---

## 9. SUCCESS METRICS

### Key Performance Indicators

| Metric | Current | Target (3 months) |
|--------|---------|-------------------|
| **schema_change Error Rate** | 15% | <5% |
| **Manual Fix Time/Week** | 6-8 hours | <2 hours |
| **Proactive Detection Rate** | 0% | >80% |
| **Auto-Recovery Rate** | 0% | >50% |
| **Overall Success Rate** | 85% | >95% |

---

## 10. CONCLUSION

### Can We Have a Dynamic System? **YES, BUT...**

**✅ What's Achievable**:
- 50-70% fewer schema change failures
- 80%+ proactive detection before failures
- 50%+ auto-recovery without human intervention
- Faster fixes when manual intervention needed

**⚠️ Limitations**:
- Complete autonomy (0% human intervention) is unrealistic
- Some changes will always need human review
- AI-assisted parsing has costs
- Banks will always surprise us with new patterns

**🎯 Realistic Goal**:
**"Self-Healing with Human Oversight"**

A system that:
1. Automatically handles 50%+ of schema changes
2. Detects 80%+ of changes proactively
3. Provides diagnostic insights for remaining 20%
4. Reduces manual maintenance by 70%

This is a **significant improvement** over current state and **achievable in 3 months**.

---

**Next Steps**: Prioritize Phase 1 implementation (multi-strategy + fuzzy selectors) for immediate 30-50% improvement.

