#!/usr/bin/env python3
"""
Show the latest collected exchange rates.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

def main():
    dsn = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
    
    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:
        print(f"❌ Database connection failed: {exc}")
        return
    
    try:
        show_latest(conn)
    finally:
        conn.close()


def show_latest(conn):
    """Show the latest collection run and rates."""
    
    print("=" * 100)
    print("📊 LATEST EXCHANGE RATE COLLECTION")
    print("=" * 100)
    print()
    
    # Get latest collection run
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, started_at, completed_at, total_sources,
                   successful_sources, failed_sources, total_records
            FROM collection_run
            ORDER BY started_at DESC
            LIMIT 1
        """)
        run = cur.fetchone()
        
        if not run:
            print("❌ No collection runs found. Run the scheduler first:")
            print("   PYTHONPATH=. python3 scheduler/run_job.py")
            return
        
        print(f"🕐 Collection Run #{run['id']}")
        print(f"   Started:    {run['started_at']}")
        print(f"   Completed:  {run['completed_at']}")
        print(f"   Duration:   {(run['completed_at'] - run['started_at']).total_seconds():.1f} seconds")
        print(f"   Success:    {run['successful_sources']}/{run['total_sources']} sources")
        print(f"   Failed:     {run['failed_sources']} sources")
        print(f"   Records:    {run['total_records']} rate observations")
        print()
        
        run_id = run['id']
    
    # Get USD rates by bank
    print("-" * 100)
    print("💵 USD RATES BY BANK (Latest Collection)")
    print("-" * 100)
    print()
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                rs.name as bank_name,
                rc.name as category,
                ro.buying_rate,
                ro.selling_rate,
                ro.effective_date,
                ro.validation_status
            FROM rate_observation ro
            JOIN rate_source rs ON ro.source_id = rs.id
            JOIN rate_category rc ON ro.category_id = rc.id
            WHERE ro.collection_run_id = %s
              AND ro.source_currency_code = 'USD'
            ORDER BY rs.name, rc.name
        """, (run_id,))
        
        rows = cur.fetchall()
        
        if rows:
            current_bank = None
            for row in rows:
                if row['bank_name'] != current_bank:
                    if current_bank is not None:
                        print()
                    current_bank = row['bank_name']
                    print(f"🏦 {current_bank}")
                
                buy = f"{float(row['buying_rate']):.4f}" if row['buying_rate'] else "N/A      "
                sell = f"{float(row['selling_rate']):.4f}" if row['selling_rate'] else "N/A      "
                status_icon = "✅" if row['validation_status'] == 'accepted' else ("⚠️" if row['validation_status'] == 'flagged' else "❌")
                
                print(f"   {status_icon} {row['category']:20s} | Buy: {buy} | Sell: {sell} | {row['effective_date']}")
        else:
            print("No USD rates found")
    
    print()
    print("-" * 100)
    print("📊 SUMMARY STATISTICS")
    print("-" * 100)
    print()
    
    # Category distribution
    with conn.cursor() as cur:
        cur.execute("""
            SELECT rc.name, COUNT(*) as count
            FROM rate_observation ro
            JOIN rate_category rc ON ro.category_id = rc.id
            WHERE ro.collection_run_id = %s
            GROUP BY rc.name
            ORDER BY count DESC
        """, (run_id,))
        
        print("Categories:")
        for row in cur.fetchall():
            print(f"  • {row[0]:20s}: {row[1]:4d} observations")
    
    print()
    
    # Currency distribution
    with conn.cursor() as cur:
        cur.execute("""
            SELECT source_currency_code, COUNT(*) as count
            FROM rate_observation
            WHERE collection_run_id = %s
            GROUP BY source_currency_code
            ORDER BY count DESC
        """, (run_id,))
        
        print("Currencies:")
        currencies = cur.fetchall()
        for i in range(0, len(currencies), 6):
            row_data = currencies[i:i+6]
            print("  " + "  ".join(f"{code:5s}({cnt:3d})" for code, cnt in row_data))
    
    print()
    
    # Validation status
    with conn.cursor() as cur:
        cur.execute("""
            SELECT validation_status, COUNT(*) as count
            FROM rate_observation
            WHERE collection_run_id = %s
            GROUP BY validation_status
            ORDER BY count DESC
        """, (run_id,))
        
        print("Validation Status:")
        for row in cur.fetchall():
            status_icons = {
                'accepted': '✅',
                'flagged': '⚠️',
                'rejected': '❌',
                'warning': '⚠️'
            }
            icon = status_icons.get(row[0], '❓')
            print(f"  {icon} {row[0]:15s}: {row[1]:4d} observations")
    
    print()
    print("=" * 100)


if __name__ == "__main__":
    main()
