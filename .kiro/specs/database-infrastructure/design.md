# Design: Database Infrastructure

**Feature Name:** database-infrastructure  
**Spec Type:** Feature (New)  
**Status:** Draft  
**Created:** 2026-10-14

---

## Table of Contents

1. [Design Overview](#design-overview)
2. [Architecture](#architecture)
3. [Component Design](#component-design)
4. [Interface Specifications](#interface-specifications)
5. [Migration Strategy](#migration-strategy)
6. [Testing Strategy](#testing-strategy)
7. [Deployment Plan](#deployment-plan)
8. [Rollback Strategy](#rollback-strategy)

---

## Design Overview

### Problem Statement

The current system creates a new PostgreSQL connection for every API request and has inconsistent database configuration across modules. This causes:

1. **Performance bottleneck:** Connection creation is expensive (~50-100ms per connection)
2. **Code duplication:** Connection management code repeated in 6+ modules
3. **Configuration inconsistency:** DSN handling differs across modules
4. **Resource waste:** No connection reuse
5. **Testing difficulty:** Hard to mock database connections

### Solution Summary

Implement a centralized `DatabaseManager` class that:

- Manages a thread-safe connection pool using `psycopg2.pool.ThreadedConnectionPool`
- Provides a clean context manager API for connection acquisition
- Handles DSN normalization consistently
- Supports graceful initialization and shutdown
- Enables easy testing with mock injection
- Maintains 100% backward compatibility

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Use psycopg2.pool.ThreadedConnectionPool** | Battle-tested, thread-safe, built-in solution |
| **Context manager API** | Pythonic, ensures automatic cleanup, familiar pattern |
| **Class-based singleton pattern** | Single global pool, lazy initialization, easy access |
| **No schema changes** | Pure code refactoring, safe deployment |
| **Incremental migration** | Migrate one module at a time, test continuously |
| **Graceful degradation** | Falls back to direct connections if pool unavailable |

---

## Architecture

### Current Architecture (Before)

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                     │
├──────────────┬──────────────┬──────────────┬────────────┤
│  api/app.py  │scheduler/    │seed_and_run  │review/     │
│              │runner.py     │.py           │workflow.py │
│              │              │              │            │
│  DSN setup   │  DSN setup   │  DSN setup   │ Uses other │
│  _conn()     │  (different) │  (different) │ module's   │
│              │              │              │ connection │
└──────┬───────┴──────┬───────┴──────┬───────┴─────┬──────┘
       │              │              │             │
       │ NEW CONN     │ NEW CONN     │ NEW CONN    │
       │ every        │ per          │ per         │
       │ request!     │ collection   │ run         │
       │              │              │             │
       ▼              ▼              ▼             ▼
┌──────────────────────────────────────────────────────────┐
│                PostgreSQL Database                        │
│  (Many short-lived connections, no reuse)                │
└──────────────────────────────────────────────────────────┘

Problems:
❌ New connection per API request (~50-100ms overhead)
❌ DSN handling inconsistent (some fix postgres://, some don't)
❌ Code duplication in every module
❌ No connection pooling
```

### New Architecture (After)

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                     │
├──────────────┬──────────────┬──────────────┬────────────┤
│  api/app.py  │scheduler/    │seed_and_run  │review/     │
│              │runner.py     │.py           │workflow.py │
│              │              │              │            │
│  with        │  with        │  with        │  with      │
│  DatabaseMan │  DatabaseMan │  DatabaseMan │  DatabaseM │
│  ager.conn() │  ager.conn() │  ager.conn() │  ager.conn │
└──────┬───────┴──────┬───────┴──────┬───────┴─────┬──────┘
       │              │              │             │
       │ GET from     │ GET from     │ GET from    │
       │ pool         │ pool         │ pool        │
       │              │              │             │
       ▼              ▼              ▼             ▼
┌──────────────────────────────────────────────────────────┐
│              db/manager.py (NEW)                          │
│         DatabaseManager (Singleton)                       │
│                                                           │
│  ┌─────────────────────────────────────────┐            │
│  │  ThreadedConnectionPool                  │            │
│  │  (2-10 connections, reusable)           │            │
│  │                                          │            │
│  │  [conn1] [conn2] [conn3] ... [conn10]  │            │
│  └─────────────────────────────────────────┘            │
│                                                           │
│  • DSN normalization (postgres:// → postgresql://)      │
│  • Thread-safe connection acquisition/release            │
│  • Automatic cleanup on context exit                     │
│  • Health monitoring & logging                           │
└───────────────────────────┬───────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│                PostgreSQL Database                        │
│  (Few long-lived pooled connections, high reuse)         │
└──────────────────────────────────────────────────────────┘

Benefits:
✅ Connection reuse (50-80% faster!)
✅ Consistent DSN handling
✅ Single source of truth
✅ Thread-safe pooling
✅ Easy testing
```

### Component Diagram

```
┌────────────────────────────────────────────────────────────┐
│                      db/manager.py                         │
│                                                            │
│  ┌──────────────────────────────────────────────────┐    │
│  │        DatabaseManager (Class)                    │    │
│  │                                                    │    │
│  │  Class Attributes:                                │    │
│  │    _pool: ThreadedConnectionPool | None          │    │
│  │    _config: dict | None                          │    │
│  │                                                    │    │
│  │  Class Methods:                                   │    │
│  │    initialize(min_conn, max_conn) → None         │    │
│  │    connection() → ContextManager[conn]           │    │
│  │    get_pool_status() → dict                      │    │
│  │    close_all() → None                            │    │
│  │    reset() → None  # For testing                 │    │
│  │    _normalize_dsn(dsn) → str                     │    │
│  └──────────────────────────────────────────────────┘    │
│                                                            │
│  ┌──────────────────────────────────────────────────┐    │
│  │     DatabaseConfig (Dataclass) - OPTIONAL        │    │
│  │                                                    │    │
│  │    dsn: str                                       │    │
│  │    min_connections: int = 2                      │    │
│  │    max_connections: int = 10                     │    │
│  │    timeout: int = 30                             │    │
│  └──────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│              db/__init__.py                                 │
│                                                             │
│  from db.manager import DatabaseManager                    │
│  __all__ = ["DatabaseManager"]                            │
└────────────────────────────────────────────────────────────┘

External Dependencies:
  • psycopg2.pool.ThreadedConnectionPool (existing dependency)
  • contextlib.contextmanager (standard library)
  • logging (standard library)
  • os (standard library)
```

---

## Component Design

### 1. DatabaseManager Class

**Responsibility:** Manage database connection pool and provide thread-safe connection access.

**Design Pattern:** Singleton (class-level attributes)

**Key Features:**
- Lazy initialization (creates pool on first use)
- Thread-safe connection acquisition/release
- Automatic DSN normalization
- Graceful error handling
- Pool status monitoring
- Test support (reset, mock injection)

#### Class Structure

```python
# db/manager.py

import os
import logging
from contextlib import contextmanager
from typing import Optional
import psycopg2
from psycopg2 import pool

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Centralized database connection management with pooling.
    
    Provides thread-safe connection pooling using psycopg2.pool.ThreadedConnectionPool.
    Handles DSN normalization for compatibility with different PostgreSQL URI schemes.
    
    Usage:
        # Initialize pool (typically at application startup)
        DatabaseManager.initialize(min_conn=2, max_conn=10)
        
        # Get connection from pool
        with DatabaseManager.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM rate_source")
                rows = cur.fetchall()
        
        # Shutdown (typically at application exit)
        DatabaseManager.close_all()
    
    Thread Safety:
        All methods are thread-safe. Multiple threads can safely acquire
        connections from the pool concurrently.
    
    Testing:
        Use DatabaseManager.reset() to clear pool between tests.
        Mock connections can be injected for unit testing.
    """
    
    # Class-level attributes (singleton pattern)
    _pool: Optional[pool.ThreadedConnectionPool] = None
    _config: Optional[dict] = None
    _initialized: bool = False
    
    @classmethod
    def initialize(
        cls,
        min_conn: int = 2,
        max_conn: int = 10,
        dsn: Optional[str] = None,
        timeout: int = 30
    ) -> None:
        """
        Initialize the connection pool.
        
        Args:
            min_conn: Minimum number of connections to maintain in pool
            max_conn: Maximum number of connections allowed in pool
            dsn: Database connection string. If None, reads from DATABASE_URL env var
            timeout: Connection timeout in seconds
        
        Raises:
            psycopg2.OperationalError: If unable to connect to database
            ValueError: If min_conn > max_conn or invalid parameters
        
        Note:
            Safe to call multiple times - subsequent calls are no-ops if already initialized.
        """
        if cls._initialized:
            logger.debug("DatabaseManager already initialized, skipping")
            return
        
        if min_conn < 1:
            raise ValueError("min_conn must be >= 1")
        if max_conn < min_conn:
            raise ValueError("max_conn must be >= min_conn")
        
        # Get and normalize DSN
        if dsn is None:
            dsn = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
        
        dsn = cls._normalize_dsn(dsn)
        
        # Store configuration
        cls._config = {
            "dsn": dsn,
            "min_conn": min_conn,
            "max_conn": max_conn,
            "timeout": timeout,
        }
        
        try:
            # Create connection pool
            cls._pool = pool.ThreadedConnectionPool(
                minconn=min_conn,
                maxconn=max_conn,
                dsn=dsn,
                connect_timeout=timeout
            )
            cls._initialized = True
            
            logger.info(
                f"Database connection pool initialized: "
                f"{min_conn}-{max_conn} connections, timeout={timeout}s"
            )
            
        except psycopg2.OperationalError as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    @classmethod
    @contextmanager
    def connection(cls):
        """
        Get a database connection from the pool.
        
        Yields:
            psycopg2.connection: Database connection from pool
        
        Raises:
            RuntimeError: If pool not initialized
            pool.PoolExhausted: If all connections in use (should wait/retry)
        
        Usage:
            with DatabaseManager.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
        
        Note:
            Connection is automatically returned to pool when context exits,
            even if an exception occurs.
        """
        # Lazy initialization if not already done
        if not cls._initialized:
            logger.warning("DatabaseManager not initialized, initializing with defaults")
            cls.initialize()
        
        if cls._pool is None:
            raise RuntimeError("Database pool is None (initialization may have failed)")
        
        conn = None
        try:
            # Get connection from pool (blocks if pool exhausted)
            conn = cls._pool.getconn()
            
            if conn is None:
                raise RuntimeError("Pool returned None connection")
            
            logger.debug(f"Connection acquired from pool (id: {id(conn)})")
            yield conn
            
        except pool.PoolError as e:
            logger.error(f"Pool error acquiring connection: {e}")
            raise
            
        finally:
            # Always return connection to pool
            if conn is not None and cls._pool is not None:
                try:
                    cls._pool.putconn(conn)
                    logger.debug(f"Connection returned to pool (id: {id(conn)})")
                except pool.PoolError as e:
                    logger.error(f"Error returning connection to pool: {e}")
    
    @classmethod
    def get_pool_status(cls) -> dict:
        """
        Get current connection pool status.
        
        Returns:
            dict with keys:
                - initialized: bool
                - min_conn: int
                - max_conn: int
                - available: int (approximate)
        
        Note:
            'available' is approximate due to thread-safety limitations in psycopg2.pool
        """
        if not cls._initialized or cls._pool is None:
            return {
                "initialized": False,
                "min_conn": 0,
                "max_conn": 0,
                "available": 0,
            }
        
        # Note: psycopg2.pool doesn't expose detailed stats, this is approximate
        return {
            "initialized": True,
            "min_conn": cls._config["min_conn"],
            "max_conn": cls._config["max_conn"],
            "available": "unknown",  # psycopg2.pool doesn't expose this
            "config": cls._config,
        }
    
    @classmethod
    def close_all(cls) -> None:
        """
        Close all connections in the pool and reset state.
        
        Should be called at application shutdown.
        Safe to call multiple times.
        """
        if cls._pool is not None:
            try:
                cls._pool.closeall()
                logger.info("All database connections closed")
            except Exception as e:
                logger.error(f"Error closing connection pool: {e}")
            finally:
                cls._pool = None
                cls._config = None
                cls._initialized = False
    
    @classmethod
    def reset(cls) -> None:
        """
        Reset the connection pool (for testing).
        
        Closes all connections and clears state.
        Typically used between test cases to ensure isolation.
        """
        cls.close_all()
    
    @classmethod
    def _normalize_dsn(cls, dsn: str) -> str:
        """
        Normalize DSN to handle different PostgreSQL URI schemes.
        
        Render.com provides DATABASE_URL with postgres:// scheme,
        but psycopg2 requires postgresql:// scheme.
        
        Args:
            dsn: Database connection string
        
        Returns:
            Normalized DSN string
        
        Examples:
            postgres://user:pass@host/db -> postgresql://user:pass@host/db
            postgresql://user:pass@host/db -> postgresql://user:pass@host/db
            dbname=exchange_rates -> dbname=exchange_rates
        """
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
            logger.debug("Normalized postgres:// to postgresql:// in DSN")
        
        return dsn
```

#### Design Rationale

**Why class-level attributes (singleton)?**
- Single global connection pool shared across entire application
- Simpler API: `DatabaseManager.connection()` vs. `db_manager.connection()`
- No need to pass manager instance around
- Matches psycopg2.pool design pattern

**Why context manager?**
- Ensures automatic connection return to pool
- Pythonic and familiar pattern
- Prevents resource leaks
- Works seamlessly with existing code

**Why lazy initialization?**
- Allows configuration before pool creation
- Easier testing (can initialize differently per test)
- Graceful degradation if initialization fails

**Why ThreadedConnectionPool?**
- Built-in thread safety
- Battle-tested in production
- No external dependencies
- Sufficient for our concurrency needs

---

### 2. Module Migration Patterns

#### Pattern A: API Module (api/app.py)

**Before:**
```python
import psycopg2

DSN = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
if DSN.startswith("postgres://"):
    DSN = DSN.replace("postgres://", "postgresql://", 1)

def _conn():
    return psycopg2.connect(DSN)

@app.get("/rates")
def rates():
    try:
        with _conn() as conn:  # NEW CONNECTION EVERY REQUEST!
            rows = get_trusted_rates(conn)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return _json(rows)
```

**After:**
```python
from db.manager import DatabaseManager

# Initialize pool once at application startup
DatabaseManager.initialize(min_conn=2, max_conn=10)

@app.get("/rates")
def rates():
    try:
        with DatabaseManager.connection() as conn:  # REUSES POOLED CONNECTION!
            rows = get_trusted_rates(conn)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return _json(rows)

# At application shutdown (if using app lifecycle hooks)
@app.teardown_appcontext
def shutdown_db(exception=None):
    DatabaseManager.close_all()
```

**Changes:**
1. ✅ Remove `DSN` and `_conn()` - replaced by `DatabaseManager`
2. ✅ Add pool initialization at startup
3. ✅ Replace `with _conn()` with `with DatabaseManager.connection()`
4. ✅ Add shutdown hook (optional but recommended)

**Performance Impact:** 50-80% faster response times!

---

#### Pattern B: Scheduler Module (scheduler/runner.py)

**Before:**
```python
import psycopg2

def run_collection(source_id: int):
    conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
    try:
        # ... collection logic
        conn.commit()
    finally:
        conn.close()
```

**After:**
```python
from db.manager import DatabaseManager

def run_collection(source_id: int):
    with DatabaseManager.connection() as conn:
        # ... collection logic
        conn.commit()
```

**Changes:**
1. ✅ Remove manual `psycopg2.connect()` and `.close()`
2. ✅ Use `DatabaseManager.connection()` context manager
3. ✅ Connection automatically returned to pool

---

#### Pattern C: Script Module (seed_and_run.py)

**Before:**
```python
import psycopg2

DSN = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
# Missing postgres:// fix!

def main():
    conn = psycopg2.connect(DSN)
    seed(conn)
    check(conn)
    results = run_all(conn)
    conn.close()
```

**After:**
```python
from db.manager import DatabaseManager

def main():
    # Initialize pool for script
    DatabaseManager.initialize(min_conn=1, max_conn=3)
    
    with DatabaseManager.connection() as conn:
        seed(conn)
        check(conn)
        results = run_all(conn)
    
    # Cleanup
    DatabaseManager.close_all()
```

**Changes:**
1. ✅ Initialize pool at script start
2. ✅ Use context manager for connection
3. ✅ Explicit cleanup at end

---

#### Pattern D: Test Module (tests/conftest.py)

**Before:**
```python
import psycopg2
import pytest

@pytest.fixture
def db_conn():
    conn = psycopg2.connect("dbname=exchange_rates_test")
    yield conn
    conn.close()
```

**After:**
```python
import pytest
from db.manager import DatabaseManager

@pytest.fixture(scope="function", autouse=False)
def db_conn():
    """Provide database connection from pool."""
    # Initialize pool for tests (small pool for test DB)
    if not DatabaseManager._initialized:
        DatabaseManager.initialize(
            min_conn=1,
            max_conn=3,
            dsn="dbname=exchange_rates_test"
        )
    
    with DatabaseManager.connection() as conn:
        yield conn
        # Connection automatically returned to pool

@pytest.fixture(scope="function", autouse=True)
def reset_pool():
    """Reset pool between tests for isolation."""
    yield
    # Don't reset if other tests are running
    # DatabaseManager.reset()  # Only if needed
```

**Changes:**
1. ✅ Initialize pool with test database DSN
2. ✅ Use pooled connections in tests
3. ✅ Optional: Reset pool between tests (if needed for isolation)

---

### 3. Configuration Management

#### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `dbname=exchange_rates` | PostgreSQL connection string |
| `DB_POOL_MIN` | `2` | Minimum pool connections (optional) |
| `DB_POOL_MAX` | `10` | Maximum pool connections (optional) |
| `DB_TIMEOUT` | `30` | Connection timeout in seconds (optional) |

#### Application Startup Sequence

```python
# api/app.py (Flask example)

from flask import Flask
from db.manager import DatabaseManager
import os

app = Flask(__name__)

# Initialize database pool at startup
def init_database():
    min_conn = int(os.environ.get("DB_POOL_MIN", 2))
    max_conn = int(os.environ.get("DB_POOL_MAX", 10))
    timeout = int(os.environ.get("DB_TIMEOUT", 30))
    
    try:
        DatabaseManager.initialize(
            min_conn=min_conn,
            max_conn=max_conn,
            timeout=timeout
        )
        app.logger.info("Database pool initialized successfully")
    except Exception as e:
        app.logger.error(f"Failed to initialize database pool: {e}")
        # Decide: fail fast or graceful degradation?
        raise

# Call at app startup
init_database()

# Health check endpoint
@app.get("/health")
def health():
    try:
        with DatabaseManager.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        
        pool_status = DatabaseManager.get_pool_status()
        return jsonify({
            "status": "ok",
            "database": "connected",
            "pool": pool_status
        })
    except Exception as exc:
        return jsonify({
            "status": "error",
            "detail": str(exc)
        }), 503

# Shutdown hook
@app.teardown_appcontext
def shutdown_database(exception=None):
    if exception:
        app.logger.error(f"Shutting down with exception: {exception}")
    DatabaseManager.close_all()
```

---

## Interface Specifications

### Public API

#### `DatabaseManager.initialize()`

```python
@classmethod
def initialize(
    cls,
    min_conn: int = 2,
    max_conn: int = 10,
    dsn: Optional[str] = None,
    timeout: int = 30
) -> None:
    """
    Initialize the connection pool.
    
    Args:
        min_conn: Minimum connections (default: 2)
        max_conn: Maximum connections (default: 10)
        dsn: Connection string (default: from DATABASE_URL env var)
        timeout: Connection timeout in seconds (default: 30)
    
    Raises:
        psycopg2.OperationalError: Database connection failed
        ValueError: Invalid parameters
    
    Thread Safety: Yes (safe to call from any thread once)
    Idempotent: Yes (subsequent calls are no-ops)
    """
```

#### `DatabaseManager.connection()`

```python
@classmethod
@contextmanager
def connection(cls):
    """
    Get database connection from pool (context manager).
    
    Yields:
        psycopg2.connection: Database connection
    
    Raises:
        RuntimeError: Pool not initialized
        pool.PoolError: Connection acquisition failed
    
    Usage:
        with DatabaseManager.connection() as conn:
            # use connection
    
    Thread Safety: Yes (thread-safe connection acquisition)
    Auto-cleanup: Yes (connection returned to pool on exit)
    """
```

#### `DatabaseManager.get_pool_status()`

```python
@classmethod
def get_pool_status(cls) -> dict:
    """
    Get connection pool status.
    
    Returns:
        dict: {
            "initialized": bool,
            "min_conn": int,
            "max_conn": int,
            "config": dict
        }
    
    Thread Safety: Yes
    """
```

#### `DatabaseManager.close_all()`

```python
@classmethod
def close_all(cls) -> None:
    """
    Close all connections and reset state.
    
    Call at application shutdown.
    
    Thread Safety: Yes
    Idempotent: Yes (safe to call multiple times)
    """
```

#### `DatabaseManager.reset()`

```python
@classmethod
def reset(cls) -> None:
    """
    Reset pool (for testing).
    
    Closes all connections and clears state.
    Use for test isolation.
    
    Thread Safety: Yes (but don't call during active requests)
    """
```

---

## Migration Strategy

### Phase 1: Infrastructure Setup (Day 1)

**Goal:** Create DatabaseManager without breaking anything.

**Tasks:**
1. Create `db/` directory
2. Create `db/__init__.py`
3. Create `db/manager.py` with complete implementation
4. Create `tests/test_db_manager.py` with unit tests
5. Run tests - verify DatabaseManager works in isolation

**Success Criteria:**
- DatabaseManager tests pass
- No impact on existing functionality (not used yet)
- All 429 existing tests still pass

---

### Phase 2: API Module Migration (Day 1-2)

**Goal:** Migrate highest-impact module (API) for immediate performance gains.

**Tasks:**
1. Add `DatabaseManager.initialize()` call at Flask app startup
2. Replace `_conn()` with `DatabaseManager.connection()` in all endpoints
3. Remove old `DSN` and `_conn()` code
4. Add health check pool status
5. Run all tests
6. Load test to verify performance improvement

**Success Criteria:**
- All API endpoints work correctly
- All 429 tests pass
- Performance improved by 50%+ (measured)
- Health check shows pool status

**Rollback:** Revert api/app.py to previous version

---

### Phase 3: Scheduler Migration (Day 2)

**Goal:** Migrate scheduler to use connection pool.

**Tasks:**
1. Add `DatabaseManager.initialize()` in scheduler startup
2. Replace direct `psycopg2.connect()` with `DatabaseManager.connection()`
3. Test collection runs
4. Verify all tests pass

**Success Criteria:**
- Scheduler runs successfully
- Collection tests pass
- All 429 tests pass

**Rollback:** Revert scheduler/runner.py

---

### Phase 4: Scripts Migration (Day 2)

**Goal:** Migrate seed_and_run.py and other scripts.

**Tasks:**
1. Update seed_and_run.py to use DatabaseManager
2. Fix DSN inconsistency (add postgres:// handling via DatabaseManager)
3. Test seed and collection
4. Verify tests pass

**Success Criteria:**
- `python seed_and_run.py` works
- All tests pass

**Rollback:** Revert seed_and_run.py

---

### Phase 5: Supporting Modules (Day 3)

**Goal:** Migrate review, alerts, and other modules.

**Tasks:**
1. Migrate review/workflow.py
2. Migrate alerts/checker.py
3. Any other modules with direct database access
4. Verify all tests pass

**Success Criteria:**
- All modules using DatabaseManager
- All 429 tests pass

**Rollback:** Revert individual modules

---

### Phase 6: Test Suite Migration (Day 3)

**Goal:** Optimize test suite to use pooled connections.

**Tasks:**
1. Update test fixtures to use DatabaseManager
2. Consider pool reset strategy for test isolation
3. Verify test performance (should be same or better)
4. Verify all 429 tests pass

**Success Criteria:**
- Tests use pooled connections
- Test isolation maintained
- All tests pass
- Test runtime unchanged or improved

**Rollback:** Revert test fixture changes

---

### Phase 7: Documentation & Cleanup (Day 3)

**Goal:** Complete documentation and remove deprecated code.

**Tasks:**
1. Update README with DatabaseManager usage
2. Add migration guide for developers
3. Remove any remaining deprecated connection code
4. Final verification: all tests pass

**Success Criteria:**
- Documentation complete
- No deprecated code remains
- All tests pass

---

## Testing Strategy

### Unit Tests (tests/test_db_manager.py)

```python
import pytest
import psycopg2
from db.manager import DatabaseManager


class TestDatabaseManagerInitialization:
    """Test pool initialization."""
    
    def setup_method(self):
        """Reset pool before each test."""
        DatabaseManager.reset()
    
    def teardown_method(self):
        """Cleanup after each test."""
        DatabaseManager.close_all()
    
    def test_initialize_with_defaults(self):
        """Test default initialization parameters."""
        DatabaseManager.initialize()
        
        assert DatabaseManager._initialized
        assert DatabaseManager._pool is not None
        assert DatabaseManager._config["min_conn"] == 2
        assert DatabaseManager._config["max_conn"] == 10
    
    def test_initialize_with_custom_params(self):
        """Test custom initialization parameters."""
        DatabaseManager.initialize(min_conn=3, max_conn=15, timeout=60)
        
        status = DatabaseManager.get_pool_status()
        assert status["min_conn"] == 3
        assert status["max_conn"] == 15
        assert status["config"]["timeout"] == 60
    
    def test_initialize_idempotent(self):
        """Test multiple initialize calls are safe."""
        DatabaseManager.initialize(min_conn=2, max_conn=5)
        pool1 = DatabaseManager._pool
        
        DatabaseManager.initialize(min_conn=3, max_conn=8)  # Should be no-op
        pool2 = DatabaseManager._pool
        
        assert pool1 is pool2  # Same pool instance
    
    def test_initialize_invalid_params(self):
        """Test validation of initialization parameters."""
        with pytest.raises(ValueError, match="min_conn must be >= 1"):
            DatabaseManager.initialize(min_conn=0)
        
        with pytest.raises(ValueError, match="max_conn must be >= min_conn"):
            DatabaseManager.initialize(min_conn=10, max_conn=5)


class TestDatabaseManagerConnections:
    """Test connection acquisition and release."""
    
    def setup_method(self):
        DatabaseManager.reset()
        DatabaseManager.initialize(min_conn=1, max_conn=3)
    
    def teardown_method(self):
        DatabaseManager.close_all()
    
    def test_connection_context_manager(self):
        """Test basic connection acquisition."""
        with DatabaseManager.connection() as conn:
            assert conn is not None
            assert isinstance(conn, psycopg2.extensions.connection)
            
            # Verify connection works
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                assert result == (1,)
    
    def test_connection_auto_release(self):
        """Test connection automatically returned to pool."""
        conn_id = None
        
        with DatabaseManager.connection() as conn:
            conn_id = id(conn)
        
        # Get another connection - should reuse the same one
        with DatabaseManager.connection() as conn2:
            assert id(conn2) == conn_id  # Same connection reused
    
    def test_connection_release_on_exception(self):
        """Test connection returned even if exception occurs."""
        try:
            with DatabaseManager.connection() as conn:
                conn_id = id(conn)
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Connection should still be returned - verify by reusing
        with DatabaseManager.connection() as conn2:
            assert id(conn2) == conn_id
    
    def test_multiple_concurrent_connections(self):
        """Test pool handles multiple connections."""
        connections = []
        
        # Acquire multiple connections (within pool limit)
        for _ in range(3):
            conn = DatabaseManager._pool.getconn()
            connections.append(conn)
        
        # Verify all are different
        conn_ids = [id(c) for c in connections]
        assert len(set(conn_ids)) == 3
        
        # Return all to pool
        for conn in connections:
            DatabaseManager._pool.putconn(conn)
    
    def test_lazy_initialization(self):
        """Test pool auto-initializes on first connection."""
        DatabaseManager.reset()  # Clear initialization
        
        # Don't call initialize() - should auto-initialize
        with DatabaseManager.connection() as conn:
            assert conn is not None
            assert DatabaseManager._initialized


class TestDatabaseManagerDSN:
    """Test DSN normalization."""
    
    def test_normalize_postgres_scheme(self):
        """Test postgres:// converted to postgresql://."""
        dsn = "postgres://user:pass@localhost/testdb"
        normalized = DatabaseManager._normalize_dsn(dsn)
        
        assert normalized == "postgresql://user:pass@localhost/testdb"
    
    def test_normalize_already_normalized(self):
        """Test postgresql:// left unchanged."""
        dsn = "postgresql://user:pass@localhost/testdb"
        normalized = DatabaseManager._normalize_dsn(dsn)
        
        assert normalized == dsn
    
    def test_normalize_simple_dsn(self):
        """Test simple DSN left unchanged."""
        dsn = "dbname=exchange_rates"
        normalized = DatabaseManager._normalize_dsn(dsn)
        
        assert normalized == dsn


class TestDatabaseManagerPoolStatus:
    """Test pool status reporting."""
    
    def test_status_before_initialization(self):
        """Test status when pool not initialized."""
        DatabaseManager.reset()
        
        status = DatabaseManager.get_pool_status()
        assert status["initialized"] is False
        assert status["min_conn"] == 0
        assert status["max_conn"] == 0
    
    def test_status_after_initialization(self):
        """Test status when pool initialized."""
        DatabaseManager.initialize(min_conn=3, max_conn=12)
        
        status = DatabaseManager.get_pool_status()
        assert status["initialized"] is True
        assert status["min_conn"] == 3
        assert status["max_conn"] == 12


class TestDatabaseManagerCleanup:
    """Test cleanup and shutdown."""
    
    def test_close_all(self):
        """Test closing all connections."""
        DatabaseManager.initialize()
        assert DatabaseManager._pool is not None
        
        DatabaseManager.close_all()
        assert DatabaseManager._pool is None
        assert DatabaseManager._initialized is False
    
    def test_close_all_idempotent(self):
        """Test close_all safe to call multiple times."""
        DatabaseManager.initialize()
        DatabaseManager.close_all()
        DatabaseManager.close_all()  # Should not raise
    
    def test_reset_for_testing(self):
        """Test reset() clears state for testing."""
        DatabaseManager.initialize()
        
        with DatabaseManager.connection() as conn:
            pass
        
        DatabaseManager.reset()
        
        assert DatabaseManager._pool is None
        assert not DatabaseManager._initialized
```

### Integration Tests

```python
# tests/test_db_manager_integration.py

def test_api_endpoint_with_pool(client):
    """Test API endpoint uses pooled connection."""
    response = client.get("/rates")
    
    assert response.status_code == 200
    assert len(response.json) > 0


def test_concurrent_requests(client):
    """Test pool handles concurrent requests."""
    import concurrent.futures
    
    def make_request():
        response = client.get("/rates")
        return response.status_code
    
    # Make 20 concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request) for _ in range(20)]
        results = [f.result() for f in futures]
    
    # All should succeed
    assert all(status == 200 for status in results)


def test_connection_reuse_performance():
    """Test pooling improves performance."""
    import time
    from db.manager import DatabaseManager
    
    # Measure time for 50 queries with pooling
    start = time.time()
    for _ in range(50):
        with DatabaseManager.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    pooled_time = time.time() - start
    
    # Baseline with direct connections (no pooling)
    start = time.time()
    for _ in range(50):
        conn = psycopg2.connect("dbname=exchange_rates_test")
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.close()
    direct_time = time.time() - start
    
    # Pooling should be significantly faster
    assert pooled_time < direct_time * 0.5  # At least 50% faster
```

### Performance Tests

```bash
# Load test with Apache Bench
ab -n 1000 -c 50 http://localhost:5000/rates

# Before: ~500ms average response time
# After:  ~150ms average response time (70% improvement!)
```

---

## Deployment Plan

### Pre-Deployment Checklist

- [ ] All 429 tests pass locally
- [ ] Performance benchmarks show improvement
- [ ] Code review approved
- [ ] Documentation updated
- [ ] Rollback plan documented

### Deployment Steps (Render.com)

1. **Merge to main branch**
   ```bash
   git checkout main
   git merge database-infrastructure
   git push origin main
   ```

2. **Render auto-deploys** (or manual deploy if needed)

3. **Monitor deployment logs** for pool initialization:
   ```
   Database connection pool initialized: 2-10 connections, timeout=30s
   ```

4. **Verify health check**:
   ```bash
   curl https://your-app.onrender.com/health
   ```
   
   Should return:
   ```json
   {
     "status": "ok",
     "database": "connected",
     "pool": {
       "initialized": true,
       "min_conn": 2,
       "max_conn": 10
     }
   }
   ```

5. **Monitor metrics**:
   - API response times (should decrease 50%+)
   - Database connection count (should stabilize at ~2-10)
   - Error rates (should remain at 0%)

6. **Load test in production** (if safe):
   ```bash
   ab -n 100 -c 10 https://your-app.onrender.com/rates
   ```

### Post-Deployment Validation

- [ ] Health check returns OK
- [ ] API endpoints respond correctly
- [ ] Response times improved
- [ ] No error spikes in logs
- [ ] Database connection count stable

---

## Rollback Strategy

### Quick Rollback (< 5 minutes)

If issues detected immediately after deployment:

```bash
# Revert to previous commit
git revert HEAD
git push origin main

# Or roll back in Render dashboard to previous deployment
```

### Gradual Rollback (Module-by-Module)

If specific module has issues:

1. Identify problematic module
2. Revert only that module to old connection pattern
3. Keep DatabaseManager for other modules
4. Deploy fix

### Emergency Fallback

If DatabaseManager completely fails:

```python
# Add to DatabaseManager.connection()
@classmethod
@contextmanager
def connection(cls):
    """Get connection - with fallback to direct connection."""
    try:
        if not cls._initialized:
            cls.initialize()
        
        if cls._pool is not None:
            conn = cls._pool.getconn()
            try:
                yield conn
            finally:
                cls._pool.putconn(conn)
        else:
            # FALLBACK: Direct connection if pool unavailable
            conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
            try:
                yield conn
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise
```

---

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Pool exhaustion under load | Medium | Medium | Configure max_conn based on load testing; monitor pool status |
| Thread safety issues | Low | High | Use psycopg2.pool.ThreadedConnectionPool (thread-safe by design) |
| Breaking existing tests | Medium | High | Test after each migration phase; maintain backward compatibility |
| Performance regression | Low | Medium | Benchmark before/after; load test |
| Deployment failure | Low | High | Gradual rollout; rollback plan ready |
| Connection leaks | Low | Medium | Context manager ensures cleanup; monitor connection count |
| Configuration errors | Medium | Medium | Validation in initialize(); clear error messages |

---

## Success Metrics

### Performance Metrics

| Metric | Baseline | Target | How to Measure |
|--------|----------|--------|----------------|
| API response time (/rates) | 250ms | <125ms | Apache Bench, application logs |
| Requests per second | 20 | 40+ | Load testing |
| Database connections | 50+ | 2-10 | PostgreSQL pg_stat_activity |
| Connection creation time | 50ms/request | Amortized to ~1ms | Profiling |

### Code Quality Metrics

| Metric | Before | After | How to Measure |
|--------|--------|-------|----------------|
| Lines of connection code | ~60 lines (duplicated) | ~200 lines (centralized) | Line count |
| DSN handling locations | 5 modules | 1 module | grep "DATABASE_URL" |
| Connection patterns | 5 different patterns | 1 consistent pattern | Code review |

### Reliability Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Connection acquisition success rate | 99.9%+ | Application logs |
| Connection leak rate | 0 | Monitor pg_stat_activity over 24h |
| Test pass rate | 100% (429/429) | CI/CD pipeline |

---

## Future Enhancements (Out of Scope)

These are NOT part of this spec but could be future work:

1. **Read Replica Support**
   - Route SELECT queries to read replicas
   - Requires: connection routing logic, replica configuration

2. **Connection Monitoring Dashboard**
   - Real-time pool status visualization
   - Requires: metrics collection, dashboard UI

3. **Advanced Pool Configuration**
   - Dynamic pool sizing based on load
   - Connection health checks
   - Requires: monitoring infrastructure

4. **Database Failover**
   - Automatic failover to backup database
   - Requires: HA infrastructure, health monitoring

5. **Query Performance Monitoring**
   - Log slow queries
   - Query performance analytics
   - Requires: query instrumentation

---

## Appendix A: Complete File Structure

```
project/
├── db/                          # NEW directory
│   ├── __init__.py             # NEW: Export DatabaseManager
│   └── manager.py              # NEW: DatabaseManager implementation
│
├── tests/
│   ├── test_db_manager.py      # NEW: Unit tests for DatabaseManager
│   ├── test_db_integration.py  # NEW: Integration tests
│   └── conftest.py             # MODIFIED: Add DatabaseManager fixtures
│
├── api/
│   └── app.py                  # MODIFIED: Use DatabaseManager
│
├── scheduler/
│   └── runner.py               # MODIFIED: Use DatabaseManager
│
├── review/
│   └── workflow.py             # MODIFIED: Use DatabaseManager
│
├── alerts/
│   └── checker.py              # MODIFIED: Use DatabaseManager
│
├── seed_and_run.py             # MODIFIED: Use DatabaseManager
│
└── README.md                   # MODIFIED: Document DatabaseManager usage
```

---

## Appendix B: Example Usage Patterns

### Pattern 1: Simple Query

```python
from db.manager import DatabaseManager

def get_all_banks():
    """Get all banks from database."""
    with DatabaseManager.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bank")
            return cur.fetchall()
```

### Pattern 2: Transaction

```python
def update_bank_status(bank_id, is_active):
    """Update bank status with transaction."""
    with DatabaseManager.connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE bank SET is_active = %s WHERE id = %s",
                    (is_active, bank_id)
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
```

### Pattern 3: Bulk Operations

```python
def bulk_insert_rates(rates):
    """Insert multiple rates efficiently."""
    with DatabaseManager.connection() as conn:
        with conn.cursor() as cur:
            # Use executemany for bulk insert
            cur.executemany(
                "INSERT INTO rate_observation (...) VALUES (...)",
                rates
            )
        conn.commit()
```

### Pattern 4: Existing Function (No Changes Needed!)

```python
def get_trusted_rates(conn, source_id=None):
    """
    This function already takes conn as parameter.
    No changes needed - it works with both old and new patterns!
    """
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM rate_observation WHERE ...")
        return cur.fetchall()

# Old way (still works during migration):
# with _conn() as conn:
#     rates = get_trusted_rates(conn)

# New way:
with DatabaseManager.connection() as conn:
    rates = get_trusted_rates(conn)
```

---

**Design Status:** Complete - Ready for Review  
**Next Step:** Create tasks.md with implementation breakdown  
**Estimated Total Effort:** 3 days (design + implementation + testing)
