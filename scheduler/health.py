import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from infrastructure.adapter_registry import default_registry
from infrastructure.rate_source_repository import RateSourceRepository

def health_check(conn, detailed: bool = True) -> dict:
    checks = {}

    checks["database"] = _check_database(conn)

    checks["adapters"] = _check_adapters()

    if detailed:
        checks["recent_success_rate"] = _check_recent_success_rate(conn)

        checks["stuck_runs"] = _check_stuck_runs(conn)

    critical_checks = ["database", "adapters"]
    healthy = all(
        checks.get(check, {}).get("status") == "ok"
        for check in critical_checks
    )

    if detailed and healthy:
        success_check = checks.get("recent_success_rate", {})
        if success_check.get("status") == "fail":
            healthy = False

    return {
        "healthy": healthy,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def _check_database(conn) -> dict:
    try:
        start = time.time()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        latency_ms = round((time.time() - start) * 1000, 2)

        if latency_ms > 1000:
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
    result = health_check(conn, detailed=False)
    return result["healthy"]

def format_health_report(health_result: dict) -> str:
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

        for key, value in check_result.items():
            if key not in ("status", "message"):
                lines.append(f"  {key}: {value}")

        if "message" in check_result:
            lines.append(f"  → {check_result['message']}")

        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
