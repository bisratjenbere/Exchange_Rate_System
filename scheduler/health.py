"""
scheduler/health.py — System health checks before collection.

Verifies database connectivity, adapter availability, and recent success rate
before starting a collection run. Prevents collection attempts when system
is degraded or unavailable.

Usage:
    from scheduler.health import health_check
    
    result = health_check(conn)
    if not result["healthy"]:
        print(f"Health check failed: {result['checks']}")
        sys.exit(1)
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from infrastructure.adapter_registry import default_registry
from infrastructure.rate_source_repository import RateSourceRepository


def health_check(conn, detailed: bool = True) -> dict:
    """
    Verify system health before collection.
    
    Args:
        conn: Database connection
        detailed: Include detailed check information (default True)
    
    Returns:
        {
            "healthy": bool,
            "checks": {
                "database": {"status": "ok|fail", "latency_ms": X},
                "adapters": {"status": "ok|fail", "loaded": X},
                "recent_success_rate": {"status": "ok|warn|fail", "rate": X},
                "stuck_runs": {"status": "ok|warn", "count": X}
            },
            "timestamp": ISO timestamp
        }
    """
    checks = {}
    
    # Check 1: Database connectivity and latency
    checks["database"] = _check_database(conn)
    
    # Check 2: Adapter registry loadable
    checks["adapters"] = _check_adapters()
    
    # Check 3: Recent success rate (last 24 hours)
    if detailed:
        checks["recent_success_rate"] = _check_recent_success_rate(conn)
        
        # Check 4: Stuck runs
        checks["stuck_runs"] = _check_stuck_runs(conn)
    
    # Overall health: all critical checks must be "ok"
    critical_checks = ["database", "adapters"]
    healthy = all(
        checks.get(check, {}).get("status") == "ok"
        for check in critical_checks
    )
    
    # Warning-level checks don't fail health, but are included
    if detailed and healthy:
        # Downgrade to unhealthy if recent success rate is critically low
        success_check = checks.get("recent_success_rate", {})
        if success_check.get("status") == "fail":
            healthy = False
    
    return {
        "healthy": healthy,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def _check_database(conn) -> dict:
    """Check database connectivity and latency."""
    try:
        start = time.time()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        latency_ms = round((time.time() - start) * 1000, 2)
        
        # Check if latency is acceptable
        if latency_ms > 1000:  # > 1 second is concerning
            return {
                "status": "warn",
                "latency_ms": latency_ms,
                "message": "High database latency"
            }
        
        return {
            "status": "ok",
            "latency_ms": latency_ms
        }
    except Exception as e:
        return {
            "status": "fail",
            "error": str(e),
            "message": "Database connection failed"
        }


def _check_adapters() -> dict:
    """Check that adapters can be loaded."""
    try:
        registry = default_registry
        adapters = registry.list_keys()
        count = len(adapters)
        
        if count == 0:
            return {
                "status": "fail",
                "loaded": 0,
                "message": "No adapters loaded"
            }
        
        # Try loading a sample adapter to verify importability
        if adapters:
            try:
                registry.get(adapters[0])
            except Exception as e:
                return {
                    "status": "warn",
                    "loaded": count,
                    "message": f"Adapter loading may be broken: {e}"
                }
        
        return {
            "status": "ok",
            "loaded": count
        }
    except Exception as e:
        return {
            "status": "fail",
            "error": str(e),
            "message": "Adapter registry unavailable"
        }


def _check_recent_success_rate(conn, hours: int = 24) -> dict:
    """
    Check success rate over recent period.
    
    Args:
        conn: Database connection
        hours: Look-back period in hours (default 24)
    
    Returns:
        Status dict with rate and threshold evaluation
    """
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status IN ('success', 'partial_success')) as succeeded
                FROM collection_run
                WHERE started_at >= %s
            """, (since,))
            row = cur.fetchone()
            
            if not row or row[0] == 0:
                return {
                    "status": "warn",
                    "rate": None,
                    "message": f"No runs in last {hours} hours",
                    "period_hours": hours
                }
            
            total, succeeded = row
            rate = succeeded / total if total > 0 else 0.0
            
            # Thresholds
            if rate >= 0.8:
                status = "ok"
            elif rate >= 0.5:
                status = "warn"
            else:
                status = "fail"
            
            return {
                "status": status,
                "rate": round(rate, 3),
                "succeeded": succeeded,
                "total": total,
                "period_hours": hours
            }
    except Exception as e:
        return {
            "status": "fail",
            "error": str(e),
            "message": "Could not check recent success rate"
        }


def _check_stuck_runs(conn, threshold_hours: int = 4) -> dict:
    """
    Check for stuck runs (started but not finished).
    
    Args:
        conn: Database connection
        threshold_hours: Consider stuck after this many hours (default 4)
    
    Returns:
        Status dict with count of stuck runs
    """
    try:
        threshold = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*), array_agg(source_id)
                FROM collection_run
                WHERE status = 'running'
                  AND started_at < %s
            """, (threshold,))
            row = cur.fetchone()
            
            count = row[0] if row else 0
            source_ids = row[1] if row and row[1] else []
            
            if count == 0:
                return {
                    "status": "ok",
                    "count": 0
                }
            
            return {
                "status": "warn",
                "count": count,
                "source_ids": source_ids,
                "message": f"{count} stuck run(s) detected",
                "threshold_hours": threshold_hours
            }
    except Exception as e:
        return {
            "status": "warn",
            "error": str(e),
            "message": "Could not check for stuck runs"
        }


def quick_health_check(conn) -> bool:
    """
    Quick health check (database + adapters only).
    
    Returns:
        True if system is healthy, False otherwise
    """
    result = health_check(conn, detailed=False)
    return result["healthy"]


def format_health_report(health_result: dict) -> str:
    """
    Format health check result as human-readable report.
    
    Args:
        health_result: Result from health_check()
    
    Returns:
        Formatted string report
    """
    lines = []
    lines.append("=" * 60)
    lines.append("HEALTH CHECK REPORT")
    lines.append("=" * 60)
    lines.append(f"Timestamp: {health_result['timestamp']}")
    lines.append(f"Overall Status: {'✓ HEALTHY' if health_result['healthy'] else '✗ UNHEALTHY'}")
    lines.append("")
    
    for check_name, check_result in health_result["checks"].items():
        status = check_result.get("status", "unknown")
        status_symbol = {
            "ok": "✓",
            "warn": "⚠",
            "fail": "✗"
        }.get(status, "?")
        
        lines.append(f"{status_symbol} {check_name.upper()}: {status}")
        
        # Add details
        for key, value in check_result.items():
            if key not in ("status", "message"):
                lines.append(f"  {key}: {value}")
        
        if "message" in check_result:
            lines.append(f"  → {check_result['message']}")
        
        lines.append("")
    
    lines.append("=" * 60)
    return "\n".join(lines)
