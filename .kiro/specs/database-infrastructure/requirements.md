# Requirements: Database Infrastructure

**Feature Name:** database-infrastructure  
**Spec Type:** Feature (New)  
**Status:** Draft  
**Created:** 2026-10-14

---

## Overview

Implement centralized database connection management with connection pooling to improve performance, ensure consistent configuration, and provide better resource management across all modules that access the PostgreSQL database.

**Current Problem:**
- Every API request creates a new database connection (very slow)
- Inconsistent DSN handling across modules (some fix `postgres://`, some don't)
- Connection management code duplicated in 5+ modules
- No connection pooling = poor API performance (50-80% slower than optimal)
- Resource leaks possible if connections not properly closed

**Expected Benefits:**
- **50-80% API performance improvement** with connection pooling
- Single source of truth for database configuration
- Consistent DSN handling across all modules
- Better resource management and connection lifecycle
- Easier testing with mock connection injection
- Foundation for future database work (read replicas, failover, etc.)

---

## Business Context

### User Impact
- **API users** - Significantly faster response times (50-80% improvement)
- **Bank data consumers** - More responsive web UI
- **Operations team** - Better database resource utilization
- **Developers** - Easier to test and maintain database code

### Technical Debt
This addresses critical technical debt identified in codebase analysis:
- Performance bottleneck: Creating connections per request
- Configuration inconsistency: DSN handling differs across modules
- Code duplication: Connection management repeated 5+ times

### Dependencies
- **No dependencies on other specs** - This is foundational infrastructure
- **Enables:** Future work on read replicas, connection monitoring, database failover

---

## Functional Requirements

### FR-1: Connection Pool Management (REQUIRED)
**Priority:** CRITICAL  
**User Story:** As a system, I need a connection pool so that database connections are reused efficiently.

**Acceptance Criteria:**
1. Connection pool initialized on application startup
2. Pool supports configurable min/max connections (default: 2 min, 10 max)
3. Connections retrieved from pool, not created per request
4. Connections automatically returned to pool after use
5. Thread-safe connection acquisition/release
6. Graceful pool shutdown on application termination

**Testing:**
- Verify multiple requests reuse pooled connections
- Verify max connection limit enforced
- Verify connections released after use
- Load test shows 50%+ performance improvement

---

### FR-2: Centralized Database Configuration (REQUIRED)
**Priority:** HIGH  
**User Story:** As a developer, I need consistent database configuration across all modules.

**Acceptance Criteria:**
1. Single source of truth for database DSN
2. Handles both `postgres://` and `postgresql://` URI schemes
3. Reads from `DATABASE_URL` environment variable
4. Provides sensible default for local development
5. Configuration loaded once at startup
6. Same DSN handling logic used everywhere

**Testing:**
- Verify `postgres://` correctly converted to `postgresql://`
- Verify default DSN used when env var missing
- Verify configuration accessible from all modules

---

### FR-3: Context Manager API (REQUIRED)
**Priority:** HIGH  
**User Story:** As a developer, I need a clean API to get database connections.

**Acceptance Criteria:**
1. Provides `with DatabaseManager.connection() as conn:` context manager
2. Automatically handles connection acquisition
3. Automatically handles connection release
4. Works with existing psycopg2 connection API
5. No breaking changes to current code patterns
6. Clear error messages if pool not initialized

**Testing:**
- Verify context manager returns valid connection
- Verify connection released on normal exit
- Verify connection released on exception
- Verify error raised if pool not initialized

---

### FR-4: Backward Compatibility (REQUIRED)
**Priority:** CRITICAL  
**User Story:** As a developer, I need existing code to continue working during migration.

**Acceptance Criteria:**
1. All 429 existing tests pass without modification
2. Existing `_conn()` patterns work unchanged during migration
3. Migration can be done incrementally (module by module)
4. No breaking changes to database query patterns
5. Connection context manager compatible with existing cursor usage

**Testing:**
- Run full test suite - all 429 tests pass
- Verify old and new patterns work side-by-side
- Integration tests with mixed old/new code

---

### FR-5: Connection Lifecycle Observability (REQUIRED)
**Priority:** MEDIUM  
**User Story:** As an operator, I need to monitor database connection health.

**Acceptance Criteria:**
1. Log pool initialization with connection parameters
2. Log warnings if pool exhaustion occurs
3. Provide method to check pool status (connections in use, available)
4. Log errors if connection acquisition fails
5. Clear error messages for configuration problems

**Testing:**
- Verify initialization logged
- Verify pool exhaustion warning logged
- Verify connection errors logged with context

---

### FR-6: Test Support (REQUIRED)
**Priority:** HIGH  
**User Story:** As a test writer, I need to mock database connections easily.

**Acceptance Criteria:**
1. Support injecting mock connections for testing
2. Provide `reset()` method to clear pool (for test isolation)
3. Support in-memory database for tests
4. Compatible with existing test fixtures
5. No impact on test performance

**Testing:**
- Verify mock connections work in tests
- Verify pool reset clears all connections
- Verify test isolation maintained

---

### FR-7: Module Migration Path (REQUIRED)
**Priority:** HIGH  
**User Story:** As a developer, I need a clear migration path for existing modules.

**Modules to migrate:**
1. `api/app.py` - Flask API (highest impact - handles all requests)
2. `scheduler/runner.py` - Collection scheduler
3. `seed_and_run.py` - Initialization script
4. `review/workflow.py` - Review workflow
5. `alerts/checker.py` - Alert checks
6. All test files - Test database access

**Acceptance Criteria:**
1. Migration can be done one module at a time
2. Each module migration is backward compatible
3. Clear before/after examples for each pattern
4. All tests pass after each module migration

**Testing:**
- Migrate one module, run all tests
- Repeat for each module
- Final verification: all modules migrated, all tests pass

---

### FR-8: Production Deployment Safety (REQUIRED)
**Priority:** CRITICAL  
**User Story:** As an operator, I need safe deployment with rollback capability.

**Acceptance Criteria:**
1. Pool initialization failures handled gracefully
2. Falls back to direct connections if pool unavailable
3. Clear error messages for deployment issues
4. Database migration not required
5. Can roll back by reverting code (no data changes)
6. Health check endpoint verifies connection pool status

**Testing:**
- Verify graceful degradation if pool init fails
- Verify health check reports pool status
- Simulate deployment scenarios

---

## Non-Functional Requirements

### NFR-1: Performance
**Requirement:** API response time improvement of 50-80% for database queries.

**Metrics:**
- Baseline: Measure current API response time for `/rates` endpoint
- Target: Reduce response time by 50% minimum
- Load test: 100 concurrent requests complete without errors

**Testing:**
- Benchmark current performance
- Benchmark with connection pooling
- Load testing with Apache Bench or similar

---

### NFR-2: Resource Utilization
**Requirement:** Efficient use of database connections.

**Metrics:**
- Max concurrent connections: 10 (configurable)
- Connection reuse rate: >90% of requests use pooled connections
- No connection leaks (all connections properly released)

**Testing:**
- Monitor connection count under load
- Verify connections released after errors
- Long-running test (8+ hours) shows stable connection count

---

### NFR-3: Maintainability
**Requirement:** Code reduction and simplification in database access patterns.

**Metrics:**
- Remove 40+ lines of duplicate connection management code
- Single source of truth for DSN handling
- Clear separation: configuration, pooling, usage

**Testing:**
- Code review confirms cleaner patterns
- Less duplication in grep searches for `psycopg2.connect`

---

### NFR-4: Testability
**Requirement:** Easier testing with mock connections.

**Metrics:**
- Test setup time unchanged or improved
- Mock injection works in all scenarios
- Test isolation maintained (no cross-test pollution)

**Testing:**
- Existing 429 tests continue to pass
- New tests can inject mock connections
- Parallel test execution works correctly

---

### NFR-5: Reliability
**Requirement:** Robust error handling and recovery.

**Metrics:**
- Graceful handling of database connection failures
- Clear error messages for operators
- No silent failures or hung requests
- Pool recovers from transient database issues

**Testing:**
- Simulate database restart
- Simulate connection timeout
- Verify error messages are actionable

---

## Success Criteria

### Minimum Viable Product (MVP)
To consider this feature complete, we must have:

1. ✅ **DatabaseManager class** with connection pooling
2. ✅ **All 429 tests passing** with no modifications
3. ✅ **API module migrated** (api/app.py) - highest performance impact
4. ✅ **Performance benchmark** showing 50%+ improvement
5. ✅ **Health check** reports connection pool status
6. ✅ **Documentation** with migration guide for remaining modules

### Full Success
For complete success, additionally:

7. ✅ **All 6 modules migrated** (API, scheduler, seed, review, alerts, tests)
8. ✅ **Connection monitoring** in place
9. ✅ **Deployment guide** with rollback procedures
10. ✅ **Load testing** validates performance under 100+ concurrent requests

---

## Out of Scope

The following are explicitly **NOT** part of this spec:

1. **Read replica support** - Future enhancement
2. **Database failover/HA** - Future enhancement
3. **Connection encryption** - Already handled by PostgreSQL/psycopg2
4. **Schema migrations** - Not needed (no schema changes)
5. **Database backup/restore** - Separate operational concern
6. **Query optimization** - Separate concern (see Spec 4: Query Builder)
7. **ORM adoption** - Not appropriate for this procedural codebase
8. **Database monitoring tools** - Operational tools, not code
9. **Connection pooling alternatives** (pgbouncer) - Code-level pooling sufficient

---

## User Stories Summary

### Epic: Database Infrastructure Foundation

**As a system administrator**, I want efficient database connection management so that the API performs optimally under load.

**As a developer**, I want consistent database configuration so that I don't have to worry about DSN formatting in every module.

**As a test writer**, I want easy connection mocking so that I can write fast, isolated unit tests.

**As an API user**, I want faster response times so that I can integrate with the exchange rate data efficiently.

**As an operations engineer**, I want connection pool visibility so that I can monitor and troubleshoot database issues.

---

## Constraints and Assumptions

### Constraints
1. **Must maintain backward compatibility** - All 429 tests must pass
2. **Must use psycopg2** - No library changes (no SQLAlchemy, no psycopg3)
3. **Must work on Render.com** - Deployment platform constraint
4. **No schema changes** - Pure code refactoring
5. **No breaking API changes** - Existing endpoints unchanged

### Assumptions
1. PostgreSQL 12+ in production (connection pooling support)
2. Python 3.11+ environment
3. Render.com provides `DATABASE_URL` environment variable
4. Current database load is <50 concurrent connections
5. Module migration can happen incrementally over 1-2 weeks

### Risks
1. **Risk:** Connection pool exhaustion under extreme load
   - **Mitigation:** Configurable pool size, monitoring, queue requests
   
2. **Risk:** Thread safety issues in connection pool
   - **Mitigation:** Use psycopg2.pool.ThreadedConnectionPool (tested library)
   
3. **Risk:** Breaking changes during migration
   - **Mitigation:** Incremental migration, test after each module
   
4. **Risk:** Performance regression in some scenarios
   - **Mitigation:** Benchmark before/after, load testing

---

## Related Work

### Depends On
- None (foundational infrastructure)

### Enables
- Spec 4: Trusted View Query Builder (better with connection pooling)
- Future: Read replica support
- Future: Connection monitoring dashboard
- Future: Database failover/HA

### Related Specs
- **Spec 1:** Adapter Base Classes - May benefit from DatabaseManager in adapters
- **Spec 2:** Pipeline Infrastructure - RateSourceRepository will use DatabaseManager

---

## Appendix: Current vs. Desired State

### Current State (Anti-patterns)

**api/app.py:**
```python
DSN = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
if DSN.startswith("postgres://"):
    DSN = DSN.replace("postgres://", "postgresql://", 1)

def _conn():
    return psycopg2.connect(DSN)

@app.get("/rates")
def rates():
    try:
        with _conn() as conn:  # New connection EVERY request!
            rows = get_trusted_rates(conn)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return _json(rows)
```

**seed_and_run.py:**
```python
DSN = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
# No postgres:// fix! Inconsistent!

conn = psycopg2.connect(DSN)
# ... use connection
conn.close()
```

**Problems:**
- ❌ New connection per request (slow!)
- ❌ Inconsistent DSN handling
- ❌ Duplicate connection code
- ❌ No connection pooling
- ❌ Manual connection management

### Desired State (Clean patterns)

**db/manager.py:**
```python
from psycopg2 import pool
from contextlib import contextmanager

class DatabaseManager:
    """Centralized database connection management with pooling."""
    
    _pool = None
    _config = None
    
    @classmethod
    def initialize(cls, min_conn=2, max_conn=10):
        """Initialize connection pool."""
        dsn = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
        
        # Handle Render's postgres:// vs psycopg2's postgresql://
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
        
        cls._config = {"dsn": dsn, "min": min_conn, "max": max_conn}
        cls._pool = pool.ThreadedConnectionPool(min_conn, max_conn, dsn)
        
        logging.info(f"Database pool initialized: {min_conn}-{max_conn} connections")
    
    @classmethod
    @contextmanager
    def connection(cls):
        """Get connection from pool with automatic release."""
        if cls._pool is None:
            cls.initialize()
        
        conn = cls._pool.getconn()
        try:
            yield conn
        finally:
            cls._pool.putconn(conn)
    
    @classmethod
    def close_all(cls):
        """Close all connections in pool."""
        if cls._pool:
            cls._pool.closeall()
            cls._pool = None
```

**api/app.py (migrated):**
```python
from db.manager import DatabaseManager

# Initialize pool once at startup
DatabaseManager.initialize(min_conn=2, max_conn=10)

@app.get("/rates")
def rates():
    try:
        with DatabaseManager.connection() as conn:  # Reuses pooled connection!
            rows = get_trusted_rates(conn)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return _json(rows)
```

**Benefits:**
- ✅ Connection pooling (50-80% faster!)
- ✅ Consistent DSN handling
- ✅ Single source of truth
- ✅ Clean context manager API
- ✅ Automatic connection release

---

## Acceptance Tests

### AT-1: Connection Pool Initialization
```python
def test_pool_initialization():
    """Verify connection pool initializes with correct parameters."""
    DatabaseManager.initialize(min_conn=2, max_conn=5)
    
    # Should have pool created
    assert DatabaseManager._pool is not None
    assert DatabaseManager._config["min"] == 2
    assert DatabaseManager._config["max"] == 5
```

### AT-2: Connection Reuse
```python
def test_connection_reuse():
    """Verify connections are reused from pool."""
    DatabaseManager.initialize(min_conn=1, max_conn=2)
    
    conn_ids = []
    for _ in range(5):
        with DatabaseManager.connection() as conn:
            conn_ids.append(id(conn))
    
    # Should reuse connections (not create 5 new ones)
    assert len(set(conn_ids)) <= 2
```

### AT-3: Performance Improvement
```python
def test_performance_improvement():
    """Verify connection pooling improves performance."""
    import time
    
    # Baseline: direct connection (10 requests)
    start = time.time()
    for _ in range(10):
        conn = psycopg2.connect(DSN)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.close()
    baseline_time = time.time() - start
    
    # With pooling: (10 requests)
    DatabaseManager.initialize()
    start = time.time()
    for _ in range(10):
        with DatabaseManager.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    pooled_time = time.time() - start
    
    # Should be at least 50% faster
    assert pooled_time < baseline_time * 0.5
```

### AT-4: DSN Normalization
```python
def test_dsn_normalization():
    """Verify postgres:// correctly converted to postgresql://."""
    import os
    
    os.environ["DATABASE_URL"] = "postgres://user:pass@host/db"
    DatabaseManager.initialize()
    
    # Should be normalized
    assert DatabaseManager._config["dsn"].startswith("postgresql://")
```

### AT-5: Backward Compatibility
```python
def test_all_tests_pass():
    """Verify all 429 existing tests still pass."""
    result = subprocess.run(["pytest", "-v"], capture_output=True)
    assert result.returncode == 0
    assert "429 passed" in result.stdout.decode()
```

---

## Definitions

- **Connection Pool:** Managed collection of database connections that can be reused
- **DSN:** Data Source Name - PostgreSQL connection string
- **psycopg2:** Python PostgreSQL adapter library
- **ThreadedConnectionPool:** Thread-safe connection pool from psycopg2.pool
- **Context Manager:** Python `with` statement pattern for resource management
- **Backward Compatible:** Existing code continues to work without modification

---

**Requirements Status:** Draft - Ready for Review  
**Next Step:** Design phase (architecture, class design, migration plan)  
**Estimated Effort:** 2-3 days implementation + testing
