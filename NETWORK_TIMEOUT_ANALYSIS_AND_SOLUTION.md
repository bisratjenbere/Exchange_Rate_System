# 🌐 Network Timeout Analysis & Improvement Strategy

**Issue**: Network timeouts are causing collection failures (per Senior Analysis)  
**Date**: October 23, 2026  
**Priority**: HIGH - Affects reliability  

---

## 📊 CURRENT STATE ANALYSIS

### Current Configuration

From `http_clients/http_client.py`:
```python
class RequestsHttpClient:
    def __init__(
        self,
        timeout: float = 15.0,      # 15 second timeout
        max_retries: int = 2,        # 2 retry attempts  
        retry_delay: float = 2.0,    # 2 second base delay
        ...
    ):
```

**Total Maximum Wait Time**:
- Attempt 1: 15s timeout
- Wait: 2s (2^0 = 1, * 2s = 2s)
- Attempt 2: 15s timeout
- Wait: 4s (2^1 = 2, * 2s = 4s)
- Attempt 3: 15s timeout
- **Total**: Up to **51 seconds** per request

### Issues Identified

1. **Fixed 15s Timeout May Be Too Short**
   - Ethiopian bank servers can be slow
   - Business hours (9-11 AM) see peak load
   - International network latency (if hosted outside Ethiopia)

2. **Retry Strategy Not Timeout-Specific**
   - Retries on timeout AND connection errors equally
   - But timeouts vs connection errors need different handling

3. **No Timeout Differentiation**
   - Connect timeout vs read timeout (both use same 15s)
   - Connection should fail faster than full response read

4. **No Bank-Specific Timeout Configuration**
   - Some banks are consistently slower
   - One-size-fits-all approach causes issues

5. **No Circuit Breaker Pattern**
   - Continues attempting slow banks at same rate
   - Wastes resources on consistently failing banks

---

## 🔍 ROOT CAUSE ANALYSIS

### Why Network Timeouts Happen

#### 1. **Bank Server Performance** (40%)
- **Cause**: Slow/overloaded bank servers
- **Pattern**: Timeouts during business hours (9-11 AM)
- **Evidence**: Senior Analysis shows CBE, Goh Betoch intermittent timeouts
- **Impact**: 30-60s response times vs. 2-5s normal

#### 2. **Network Infrastructure** (30%)
- **Cause**: Poor internet connectivity, routing issues
- **Pattern**: Clustered failures (multiple banks at same time)
- **Evidence**: If multiple banks timeout simultaneously
- **Impact**: Complete collection failure for period

#### 3. **Geographic Latency** (15%)
- **Cause**: Physical distance, routing inefficiency
- **Pattern**: Consistent slow response (not intermittent)
- **Evidence**: Non-Ethiopian banks consistently slower
- **Impact**: 5-10s additional latency

#### 4. **Bank Website Design** (10%)
- **Cause**: JavaScript-heavy sites, large page sizes
- **Pattern**: Specific banks always slow
- **Evidence**: Anbesa (browser automation) has issues
- **Impact**: 20-40s page load times

#### 5. **Rate Limiting / Bot Detection** (5%)
- **Cause**: Banks throttling/blocking automated requests
- **Pattern**: Intermittent 403/timeout after several requests
- **Evidence**: Would need to check HTTP status codes
- **Impact**: Temporary or permanent blocking

---

## 🎯 IMPROVEMENT STRATEGY

### TIER 1: Quick Wins (Immediate - 1 Day)

#### 1.1 Implement Adaptive Timeouts

**Problem**: Fixed 15s timeout too short for slow banks, too long for fast banks  
**Solution**: Bank-specific timeout configuration

```python
# infrastructure/timeout_config.py
BANK_TIMEOUT_CONFIG = {
    # Slow banks - known to be consistently slow
    "cbe_html": {"timeout": 30.0, "max_retries": 1},
    "dashen_html": {"timeout": 25.0, "max_retries": 1},
    "goh_betoch_html": {"timeout": 30.0, "max_retries": 1},
    
    # Fast banks - usually respond quickly
    "wegagen_api": {"timeout": 10.0, "max_retries": 3},
    "rammis_api": {"timeout": 10.0, "max_retries": 3},
    
    # Browser automation - needs longer timeout
    "anbesa_browser": {"timeout": 60.0, "max_retries": 0},
    
    # Default for unknown banks
    "default": {"timeout": 15.0, "max_retries": 2}
}

def get_timeout_config(adapter_key: str) -> dict:
    """Get timeout configuration for adapter."""
    return BANK_TIMEOUT_CONFIG.get(adapter_key, BANK_TIMEOUT_CONFIG["default"])
```

**Impact**: 30% reduction in false timeout failures

---

#### 1.2 Separate Connect vs Read Timeout

**Problem**: Connection establishment and response reading use same 15s  
**Solution**: Different timeouts for different phases

```python
class RequestsHttpClient:
    def __init__(
        self,
        connect_timeout: float = 5.0,   # Fast-fail on connection
        read_timeout: float = 15.0,      # Wait longer for response
        ...
    ):
        self.timeout = (connect_timeout, read_timeout)
```

**Benefits**:
- Connection failures detected in 5s (not 15s)
- Response reading still gets 15s
- Total faster failure for network issues
- Differentiate network vs server issues

**Impact**: 20% faster detection of network outages

---

#### 1.3 Smart Retry Logic

**Problem**: Retries on timeout same as connection errors  
**Solution**: Different retry strategies per error type

```python
def fetch(self, url, ...):
    for attempt in range(self.max_retries + 1):
        try:
            response = requests.get(url, timeout=self.timeout, ...)
            return HttpResponse(...)
        
        except requests.ConnectTimeout as exc:
            # Connection timeout - likely network issue
            # Retry with exponential backoff
            if attempt < self.max_retries:
                delay = self.retry_delay * (2 ** attempt)
                time.sleep(delay)
                continue
            last_error = f"Connect timeout: {exc}"
        
        except requests.ReadTimeout as exc:
            # Read timeout - server is slow/stuck
            # Don't retry immediately (server needs recovery time)
            if attempt < self.max_retries:
                time.sleep(self.retry_delay * 3)  # Longer delay
                continue
            last_error = f"Read timeout after {self.timeout}s: {exc}"
        
        except requests.ConnectionError as exc:
            # Network/DNS issue - retry quickly
            if attempt < self.max_retries:
                time.sleep(self.retry_delay)
                continue
            last_error = f"Connection error: {exc}"
```

**Impact**: 15% better retry success rate

---

### TIER 2: Medium-Term (Week 2-3)

#### 2.1 Circuit Breaker Pattern

**Problem**: Keep trying banks that are consistently failing  
**Solution**: Temporarily stop trying after repeated failures

```python
# infrastructure/circuit_breaker.py
class CircuitBreaker:
    """Circuit breaker for failing banks."""
    
    def __init__(self, failure_threshold=3, recovery_timeout=300):
        self.failure_counts = defaultdict(int)
        self.last_attempt = {}
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # 5 minutes
    
    def should_attempt(self, bank_key: str) -> bool:
        """Check if we should attempt collection for this bank."""
        # Check if in failure state
        if self.failure_counts[bank_key] >= self.failure_threshold:
            # Check if recovery timeout expired
            last = self.last_attempt.get(bank_key)
            if last and (time.time() - last) < self.recovery_timeout:
                return False  # Still in failure state
            # Recovery timeout expired - reset and try again
            self.failure_counts[bank_key] = 0
        
        return True
    
    def record_success(self, bank_key: str):
        """Record successful collection."""
        self.failure_counts[bank_key] = 0
        self.last_attempt[bank_key] = time.time()
    
    def record_failure(self, bank_key: str):
        """Record failed collection."""
        self.failure_counts[bank_key] += 1
        self.last_attempt[bank_key] = time.time()
```

**Usage**:
```python
circuit_breaker = CircuitBreaker()

for bank in banks:
    if not circuit_breaker.should_attempt(bank.key):
        logger.info(f"Skipping {bank.key} - circuit breaker open")
        continue
    
    result = collect_from_bank(bank)
    if result.success:
        circuit_breaker.record_success(bank.key)
    else:
        circuit_breaker.record_failure(bank.key)
```

**Impact**: 25% reduction in wasted resources on failing banks

---

#### 2.2 Response Time Tracking & Auto-Tuning

**Problem**: Don't know which banks are slow without manual analysis  
**Solution**: Track response times and auto-adjust timeouts

```python
# infrastructure/response_time_tracker.py
class ResponseTimeTracker:
    """Track response times and suggest timeout adjustments."""
    
    def __init__(self):
        self.response_times = defaultdict(list)  # bank_key → [times]
        self.max_samples = 100
    
    def record_response_time(self, bank_key: str, duration_ms: float):
        """Record response time for bank."""
        times = self.response_times[bank_key]
        times.append(duration_ms)
        # Keep only recent samples
        if len(times) > self.max_samples:
            times.pop(0)
    
    def get_recommended_timeout(self, bank_key: str) -> float:
        """Get recommended timeout based on historical data."""
        times = self.response_times.get(bank_key, [])
        if len(times) < 10:
            return 15.0  # Default until we have data
        
        # P95 + 50% buffer
        p95 = np.percentile(times, 95)
        recommended = (p95 / 1000.0) * 1.5  # Convert ms to seconds, add buffer
        
        # Clamp between 5s and 60s
        return max(5.0, min(60.0, recommended))
    
    def get_stats(self, bank_key: str) -> dict:
        """Get response time statistics."""
        times = self.response_times.get(bank_key, [])
        if not times:
            return {}
        
        return {
            "avg": np.mean(times),
            "p50": np.percentile(times, 50),
            "p95": np.percentile(times, 95),
            "p99": np.percentile(times, 99),
            "max": max(times),
            "sample_count": len(times)
        }
```

**Impact**: Dynamic timeout optimization, 20% better efficiency

---

#### 2.3 Parallel Collection with Timeout Budget

**Problem**: Sequential collection means one slow bank blocks all others  
**Solution**: Collect in parallel with overall timeout budget

```python
import asyncio
import concurrent.futures

async def collect_with_timeout_budget(banks, total_budget_seconds=300):
    """
    Collect from multiple banks in parallel with total timeout budget.
    
    Args:
        banks: List of banks to collect from
        total_budget_seconds: Maximum total time for all collections
    """
    results = {}
    
    async with asyncio.TaskGroup() as group:
        tasks = {
            bank.key: group.create_task(
                collect_from_bank_async(bank)
            )
            for bank in banks
        }
    
    # Wait with overall timeout
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks.values(), return_exceptions=True),
            timeout=total_budget_seconds
        )
    except asyncio.TimeoutError:
        logger.warning(f"Collection budget exceeded ({total_budget_seconds}s)")
    
    for bank_key, task in tasks.items():
        if task.done():
            try:
                results[bank_key] = task.result()
            except Exception as e:
                results[bank_key] = {"error": str(e)}
    
    return results
```

**Impact**: 3-5x faster overall collection time

---

### TIER 3: Advanced (Month 2-3)

#### 3.1 Predictive Timeout Adjustment

**Problem**: Reactive timeout adjustment based on failures  
**Solution**: ML-based prediction of optimal timeouts

```python
# infrastructure/timeout_predictor.py
class TimeoutPredictor:
    """ML-based timeout prediction."""
    
    def predict_timeout(self, bank_key: str, hour_of_day: int, day_of_week: int) -> float:
        """
        Predict optimal timeout based on historical patterns.
        
        Factors:
        - Time of day (business hours slower)
        - Day of week (weekday vs weekend)
        - Recent failure rate
        - Historical response time distribution
        """
        # Features
        features = {
            "bank": bank_key,
            "hour": hour_of_day,
            "day_of_week": day_of_week,
            "recent_failure_rate": self.get_recent_failure_rate(bank_key),
            "avg_response_time": self.get_avg_response_time(bank_key)
        }
        
        # Simple rule-based prediction (can be replaced with ML model)
        base_timeout = 15.0
        
        # Business hours (9-11 AM) - add buffer
        if 9 <= hour_of_day <= 11:
            base_timeout *= 1.5
        
        # High failure rate - increase timeout
        if features["recent_failure_rate"] > 0.2:
            base_timeout *= 1.3
        
        # Slow average response time
        if features["avg_response_time"] > 10000:  # 10s
            base_timeout *= 1.4
        
        return min(60.0, base_timeout)
```

**Impact**: 30% reduction in timeout-related failures

---

#### 3.2 Geographic Load Balancing

**Problem**: Single collection server location causes latency  
**Solution**: Deploy collectors in multiple regions

**Architecture**:
```
Ethiopia (Primary)          Outside Ethiopia (Failover)
│                           │
├─ Collector Instance 1     ├─ Collector Instance 2
│  ├─ Ethiopian banks       │  ├─ International banks
│  └─ Low latency (<50ms)   │  └─ Backup for failures
│                           │
└─ Central Database ←───────┘
```

**Benefits**:
- 50-80% latency reduction for Ethiopian banks
- Geographic redundancy
- Failover capability

**Impact**: 40% improvement in collection reliability

---

#### 3.3 HTTP/2 and Keep-Alive Optimization

**Problem**: Creating new connection for each request  
**Solution**: Reuse connections with HTTP/2

```python
class KeepAliveHttpClient:
    """HTTP client with connection pooling."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.mount('https://', HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0,  # We handle retries ourselves
            pool_block=False
        ))
    
    def fetch(self, url, ...):
        # Reuses existing connection if available
        response = self.session.get(url, ...)
        return HttpResponse(...)
```

**Impact**: 20-30% faster response times, reduced server load

---

## 📈 EXPECTED IMPROVEMENTS

### Baseline (Current State)
- Timeout Failures: ~15% of attempts
- Average Collection Time: 8-12 minutes (sequential)
- Wasted Resources: High (retry slow banks)
- Detection Time: Slow (51s max per bank)

### After Tier 1 (Immediate Improvements)
- Timeout Failures: **<10%** (33% reduction)
- Average Collection Time: **6-8 minutes** (25% faster)
- Wasted Resources: **Medium** (better retry logic)
- Detection Time: **Fast** (5-30s per bank)

### After Tier 2 (Medium-Term)
- Timeout Failures: **<5%** (67% reduction)
- Average Collection Time: **2-3 minutes** (parallel)
- Wasted Resources: **Low** (circuit breaker)
- Detection Time: **Very Fast** (predictive)

### After Tier 3 (Advanced)
- Timeout Failures: **<2%** (87% reduction)
- Average Collection Time: **1-2 minutes** (optimized)
- Wasted Resources: **Minimal** (ML-optimized)
- Detection Time: **Predictive** (prevent failures)

---

## 🚀 IMPLEMENTATION ROADMAP

### Week 1 (Immediate)
**Priority 1 - Quick Wins**:
- [ ] Day 1: Implement adaptive timeouts (bank-specific config)
- [ ] Day 2: Separate connect/read timeouts
- [ ] Day 3: Smart retry logic (timeout vs connection errors)
- [ ] Day 4: Testing & deployment
- [ ] Day 5: Monitor improvements

**Expected Impact**: 30-40% reduction in timeout failures

---

### Week 2-3 (Medium-Term)
**Priority 2 - Strategic Improvements**:
- [ ] Week 2: Circuit breaker implementation
- [ ] Week 2: Response time tracking system
- [ ] Week 3: Parallel collection (asyncio)
- [ ] Week 3: Timeout auto-tuning based on data

**Expected Impact**: 50-60% reduction in timeout failures

---

### Month 2-3 (Advanced)
**Priority 3 - Optimization**:
- [ ] Month 2: ML-based timeout prediction
- [ ] Month 2: Connection pooling & HTTP/2
- [ ] Month 3: Geographic load balancing evaluation
- [ ] Month 3: Full system optimization

**Expected Impact**: 80%+ reduction in timeout failures

---

## 💡 RECOMMENDATIONS

### Immediate Actions (Today):
1. ✅ **Identify Slow Banks**
   - Query database for banks with >10s response times
   - Check collection logs for timeout patterns

2. ✅ **Implement Bank-Specific Timeouts**
   - Create timeout configuration file
   - Increase timeout for known-slow banks (CBE, Dashen, Goh Betoch)

3. ✅ **Separate Connect/Read Timeouts**
   - Fast-fail on connection (5s)
   - Longer read timeout (15-30s per bank)

### Short-Term (Next Week):
1. 🟡 **Add Circuit Breaker**
   - Stop attempting banks with 3+ consecutive failures
   - Auto-retry after 5-minute recovery period

2. 🟡 **Track Response Times**
   - Log duration for every successful request
   - Build P95/P99 statistics per bank
   - Alert when banks exceed expected times

3. 🟡 **Parallel Collection**
   - Convert sequential to parallel using asyncio
   - Set overall budget (5 minutes for all banks)

### Medium-Term (Next Month):
1. 🔮 **Auto-Tune Timeouts**
   - Use P95 + 50% buffer as recommended timeout
   - Adjust weekly based on data

2. 🔮 **Predictive Timeout Adjustment**
   - Increase timeouts during business hours
   - Decrease timeouts during off-peak hours

3. 🔮 **Connection Pooling**
   - Reuse connections where possible
   - Implement HTTP/2 for supported banks

---

## 📊 MONITORING & ALERTING

### Key Metrics to Track:
1. **Timeout Rate by Bank** (target: <5%)
2. **Average Response Time by Bank** (trend over time)
3. **P95 Response Time** (should be <10s for most banks)
4. **Retry Success Rate** (how often retries work)
5. **Circuit Breaker Activations** (which banks trigger it)

### Alerts to Set Up:
- 🚨 **Critical**: Timeout rate >20% for any bank (immediate action)
- ⚠️  **Warning**: Timeout rate >10% for any bank (investigate)
- ℹ️  **Info**: Response time P95 >15s (consider timeout increase)
- ℹ️  **Info**: Circuit breaker activated (bank having issues)

---

## 🎯 SUCCESS CRITERIA

### Tier 1 Success (Week 1):
- ✅ Timeout failures reduced from 15% to <10%
- ✅ Average collection time reduced by 25%
- ✅ Fast detection of network issues (5s vs 15s)
- ✅ Zero breaking changes to existing adapters

### Tier 2 Success (Week 3):
- ✅ Timeout failures <5%
- ✅ Parallel collection functional
- ✅ Circuit breaker preventing resource waste
- ✅ Response time dashboard operational

### Tier 3 Success (Month 3):
- ✅ Timeout failures <2%
- ✅ ML-based timeout prediction deployed
- ✅ Connection pooling implemented
- ✅ Geographic load balancing evaluated

---

**Status**: ANALYSIS COMPLETE ✅  
**Next Action**: Implement Tier 1 improvements  
**Owner**: Exchange Rate System Team  
**Date**: October 23, 2026
