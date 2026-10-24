#!/usr/bin/env python3
"""
Analyze network timeout patterns in collection history.

Investigates:
1. Which banks have timeout issues
2. When timeouts occur (time of day, day of week)
3. Timeout vs success patterns
4. Network vs schema_change errors
5. Response time trends
"""
import os
from datetime import datetime, timedelta
from collections import defaultdict
import psycopg2
from psycopg2.extras import RealDictCursor

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")

def analyze_failure_patterns():
    """Analyze failure patterns for high-failure banks."""
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Banks with <80% success rate
    problem_banks = ['hijra', 'ahadu', 'awash', 'addis', 'national']
    
    print("=" * 80)
    print("NETWORK TIMEOUT & FAILURE PATTERN ANALYSIS")
    print("=" * 80)
    print()
    
    for bank_key in problem_banks:
        print(f"\n{'=' * 80}")
        print(f"🔍 ANALYZING: {bank_key.upper()} BANK")
        print(f"{'=' * 80}\n")
        
        # Find the actual adapter_key for this bank
        cur.execute("""
            SELECT adapter_key
            FROM rate_source
            WHERE adapter_key ILIKE %s
            LIMIT 1
        """, (f'%{bank_key}%',))
        
        adapter_row = cur.fetchone()
        if not adapter_row:
            print(f"⚠️  No adapter found for {bank_key}")
            continue
        
        adapter_key = adapter_row['adapter_key']
        print(f"Adapter Key: {adapter_key}\n")
        
        # Get failure breakdown
        cur.execute("""
            SELECT 
                cr.status,
                cr.error_code,
                COUNT(*) as count,
                ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as percentage
            FROM collection_run cr
            JOIN rate_source rs ON cr.source_id = rs.id
            WHERE rs.adapter_key = %s
                AND cr.started_at > NOW() - INTERVAL '30 days'
            GROUP BY cr.status, cr.error_code
            ORDER BY count DESC
        """, (adapter_key,))
        
        failures = cur.fetchall()
        
        print("📊 FAILURE BREAKDOWN (Last 30 Days):")
        print("-" * 80)
        for row in failures:
            status_icon = "✅" if row['status'] == 'success' else "❌"
            print(f"{status_icon} {row['status']:12} | {row['error_code'] or 'N/A':20} | "
                  f"{row['count']:4} runs ({row['percentage']:5.1f}%)")
        
        # Time-of-day analysis for failures
        cur.execute("""
            SELECT 
                EXTRACT(HOUR FROM cr.started_at) as hour,
                cr.status,
                COUNT(*) as count
            FROM collection_run cr
            JOIN rate_source rs ON cr.source_id = rs.id
            WHERE rs.adapter_key = %s
                AND cr.started_at > NOW() - INTERVAL '7 days'
            GROUP BY EXTRACT(HOUR FROM cr.started_at), cr.status
            ORDER BY hour, status
        """, (adapter_key,))
        
        hourly_data = defaultdict(lambda: {'success': 0, 'failed': 0})
        for row in cur.fetchall():
            hour = int(row['hour'])
            status = row['status']
            count = row['count']
            hourly_data[hour][status] = count
        
        print("\n⏰ TIME-OF-DAY PATTERN (Last 7 Days):")
        print("-" * 80)
        print("Hour | Success | Failed | Total | Failure Rate")
        print("-" * 80)
        
        for hour in sorted(hourly_data.keys()):
            success = hourly_data[hour]['success']
            failed = hourly_data[hour]['failed']
            total = success + failed
            failure_rate = (failed / total * 100) if total > 0 else 0
            
            bar = "█" * int(failure_rate / 5)  # Visual bar
            print(f"{hour:4d} | {success:7d} | {failed:6d} | {total:5d} | "
                  f"{failure_rate:5.1f}% {bar}")
        
        # Check for timeout-specific errors
        cur.execute("""
            SELECT 
                cr.error_summary,
                COUNT(*) as count
            FROM collection_run cr
            JOIN rate_source rs ON cr.source_id = rs.id
            WHERE rs.adapter_key = %s
                AND cr.status = 'failed'
                AND cr.started_at > NOW() - INTERVAL '30 days'
                AND (
                    cr.error_summary ILIKE '%timeout%' OR
                    cr.error_summary ILIKE '%timed out%' OR
                    cr.error_summary ILIKE '%connection%' OR
                    cr.error_code = 'timeout'
                )
            GROUP BY cr.error_summary
            ORDER BY count DESC
            LIMIT 10
        """, (adapter_key,))
        
        timeout_errors = cur.fetchall()
        
        if timeout_errors:
            print("\n🌐 NETWORK/TIMEOUT ERRORS (Last 30 Days):")
            print("-" * 80)
            for row in timeout_errors:
                msg = row['error_summary'] or 'N/A'
                print(f"  • {msg[:70]}... ({row['count']} times)")
        
        # Recent success/failure timeline
        cur.execute("""
            SELECT 
                DATE(cr.started_at) as date,
                cr.status,
                COUNT(*) as count
            FROM collection_run cr
            JOIN rate_source rs ON cr.source_id = rs.id
            WHERE rs.adapter_key = %s
                AND cr.started_at > NOW() - INTERVAL '14 days'
            GROUP BY DATE(cr.started_at), cr.status
            ORDER BY date DESC, status
        """, (adapter_key,))
        
        timeline = defaultdict(lambda: {'success': 0, 'failed': 0})
        for row in cur.fetchall():
            date = row['date']
            status = row['status']
            count = row['count']
            timeline[date][status] = count
        
        print("\n📅 RECENT TIMELINE (Last 14 Days):")
        print("-" * 80)
        print("Date       | Success | Failed | Success Rate")
        print("-" * 80)
        
        for date in sorted(timeline.keys(), reverse=True):
            success = timeline[date]['success']
            failed = timeline[date]['failed']
            total = success + failed
            success_rate = (success / total * 100) if total > 0 else 0
            
            trend = "🟢" if success_rate > 85 else "🟡" if success_rate > 70 else "🔴"
            print(f"{date} | {success:7d} | {failed:6d} | {success_rate:5.1f}% {trend}")
        
        # Check for response time issues (if stored)
        cur.execute("""
            SELECT 
                AVG(cr.duration_ms / 1000.0) as avg_duration,
                MAX(cr.duration_ms / 1000.0) as max_duration,
                MIN(cr.duration_ms / 1000.0) as min_duration,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY cr.duration_ms / 1000.0) as p95_duration
            FROM collection_run cr
            JOIN rate_source rs ON cr.source_id = rs.id
            WHERE rs.adapter_key = %s
                AND cr.status = 'success'
                AND cr.duration_ms IS NOT NULL
                AND cr.started_at > NOW() - INTERVAL '7 days'
        """, (adapter_key,))
        
        duration_stats = cur.fetchone()
        
        if duration_stats and duration_stats['avg_duration']:
            print("\n⏱️  RESPONSE TIME STATISTICS (Successful runs, Last 7 Days):")
            print("-" * 80)
            print(f"  Average:  {duration_stats['avg_duration']:.2f}s")
            print(f"  P95:      {duration_stats['p95_duration']:.2f}s")
            print(f"  Max:      {duration_stats['max_duration']:.2f}s")
            print(f"  Min:      {duration_stats['min_duration']:.2f}s")
            
            if duration_stats['avg_duration'] > 30:
                print(f"  ⚠️  WARNING: Average response time is high (>{30}s)")
    
    cur.close()
    conn.close()


def analyze_timeout_vs_schema_change():
    """Compare timeout errors vs schema_change errors."""
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    print("\n\n" + "=" * 80)
    print("TIMEOUT vs SCHEMA_CHANGE COMPARISON (All Banks)")
    print("=" * 80)
    print()
    
    cur.execute("""
        SELECT 
            rs.adapter_key,
            COUNT(*) FILTER (WHERE cr.error_code = 'timeout') as timeout_errors,
            COUNT(*) FILTER (WHERE cr.error_code = 'schema_change') as schema_errors,
            COUNT(*) FILTER (WHERE cr.error_code NOT IN ('timeout', 'schema_change') AND cr.status = 'failed') as other_errors,
            COUNT(*) FILTER (WHERE cr.status = 'success') as successes,
            COUNT(*) as total_runs,
            ROUND(COUNT(*) FILTER (WHERE cr.error_code = 'timeout') * 100.0 / COUNT(*), 1) as timeout_pct,
            ROUND(COUNT(*) FILTER (WHERE cr.error_code = 'schema_change') * 100.0 / COUNT(*), 1) as schema_pct
        FROM collection_run cr
        JOIN rate_source rs ON cr.source_id = rs.id
        WHERE cr.started_at > NOW() - INTERVAL '30 days'
        GROUP BY rs.adapter_key
        HAVING COUNT(*) FILTER (WHERE cr.error_code IN ('timeout', 'schema_change')) > 0
        ORDER BY timeout_errors DESC, schema_errors DESC
    """)
    
    results = cur.fetchall()
    
    print("Bank          | Timeout | Schema | Other | Success | Total | TO% | SC%")
    print("-" * 80)
    
    for row in results:
        bank = row['adapter_key'][:12].ljust(12)
        print(f"{bank} | {row['timeout_errors']:7d} | {row['schema_errors']:6d} | "
              f"{row['other_errors']:5d} | {row['successes']:7d} | {row['total_runs']:5d} | "
              f"{row['timeout_pct']:4.1f}% | {row['schema_pct']:4.1f}%")
    
    cur.close()
    conn.close()


def analyze_network_patterns():
    """Analyze network-related patterns."""
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    print("\n\n" + "=" * 80)
    print("NETWORK PATTERNS ANALYSIS")
    print("=" * 80)
    print()
    
    # Check if errors are clustered in time (network outages)
    cur.execute("""
        WITH error_runs AS (
            SELECT 
                rs.adapter_key,
                cr.started_at,
                cr.error_code,
                LAG(cr.started_at) OVER (PARTITION BY rs.adapter_key ORDER BY cr.started_at) as prev_error_time
            FROM collection_run cr
            JOIN rate_source rs ON cr.source_id = rs.id
            WHERE cr.status = 'failed'
                AND cr.error_code IN ('timeout', 'connection_error', 'network_error')
                AND cr.started_at > NOW() - INTERVAL '7 days'
        )
        SELECT 
            adapter_key,
            COUNT(*) as error_count,
            COUNT(*) FILTER (WHERE started_at - prev_error_time < INTERVAL '1 hour') as clustered_errors,
            ROUND(COUNT(*) FILTER (WHERE started_at - prev_error_time < INTERVAL '1 hour') * 100.0 / COUNT(*), 1) as cluster_pct
        FROM error_runs
        WHERE prev_error_time IS NOT NULL
        GROUP BY adapter_key
        HAVING COUNT(*) > 5
        ORDER BY cluster_pct DESC
    """)
    
    clustering = cur.fetchall()
    
    if clustering:
        print("🔗 ERROR CLUSTERING (Errors within 1 hour of each other):")
        print("-" * 80)
        print("Bank          | Total Errors | Clustered | Cluster %")
        print("-" * 80)
        
        for row in clustering:
            bank = row['adapter_key'][:12].ljust(12)
            cluster_bar = "█" * int(row['cluster_pct'] / 5)
            print(f"{bank} | {row['error_count']:12d} | {row['clustered_errors']:9d} | "
                  f"{row['cluster_pct']:8.1f}% {cluster_bar}")
        
        print("\n💡 High clustering suggests network outages or infrastructure issues")
    
    cur.close()
    conn.close()


def main():
    """Run all timeout analyses."""
    try:
        analyze_failure_patterns()
        analyze_timeout_vs_schema_change()
        analyze_network_patterns()
        
        print("\n\n" + "=" * 80)
        print("🎯 ANALYSIS COMPLETE")
        print("=" * 80)
        print("\nNext steps:")
        print("1. Check which errors are timeouts vs schema_change")
        print("2. Identify time-of-day patterns for timeouts")
        print("3. Look for network infrastructure issues")
        print("4. Consider retry strategies for timeouts")
        print("5. Investigate slow-responding banks")
        
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
