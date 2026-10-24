#!/usr/bin/env python3
"""
Analyze today's exchange rate collection.
Shows summary statistics and rates by bank and category.
"""
import os
import sys
from datetime import date
from decimal import Decimal
import psycopg2
from psycopg2.extras import RealDictCursor

def main():
    dsn = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
    
    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:
        print(f"❌ Database connection failed: {exc}")
        sys.exit(1)
    
    try:
        analyze_rates(conn)
    finally:
        conn.close()


def analyze_rates(conn):
    """Analyze today's exchange rates."""
    today = date.today()
    
    print("=" * 80)
    print(f"📊 EXCHANGE RATE ANALYSIS - {today}")
    print("=" * 80)
    print()
    
    # 1. Overall Statistics
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) as total_records,
                   COUNT(DISTINCT source_id) as sources_with_data,
                   COUNT(DISTINCT source_currency_code) as currencies,
                   COUNT(DISTINCT category) as categories
            FROM public.rate_observation
            WHERE collection_date = %s
        """, (today,))
        stats = cur.fetchone()
        
        if stats and stats[0] > 0:
            print(f"✅ Total Records: {stats[0]}")
            print(f"🏦 Banks with Data: {stats[1]}")
            print(f"💱 Currencies: {stats[2]}")
            print(f"📁 Categories: {stats[3]}")
        else:
            print("❌ No data collected for today yet")
            print()
            print("Run the collection job first:")
            print("  PYTHONPATH=. python3 scheduler/run_job.py")
            return
    
    print()
    print("-" * 80)
    print("💵 USD RATES BY BANK")
    print("-" * 80)
    print()
    
    # 2. USD Rates by Bank and Category
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT s.name as bank_name,
                   ro.category,
                   ro.buying_rate,
                   ro.selling_rate,
                   ro.effective_date,
                   ro.validation_status
            FROM public.rate_observation ro
            JOIN public.rate_source s ON ro.source_id = s.id
            WHERE ro.collection_date = %s
              AND ro.source_currency_code = 'USD'
            ORDER BY s.name, ro.category
        """, (today,))
        
        rows = cur.fetchall()
        
        if rows:
            current_bank = None
            for row in rows:
                if row['bank_name'] != current_bank:
                    if current_bank is not None:
                        print()
                    current_bank = row['bank_name']
                    print(f"🏦 {current_bank}")
                
                buy = f"{row['buying_rate']:.4f}" if row['buying_rate'] else "N/A"
                sell = f"{row['selling_rate']:.4f}" if row['selling_rate'] else "N/A"
                status_icon = "✅" if row['validation_status'] == 'accepted' else "⚠️"
                
                print(f"   {status_icon} {row['category']:20s} | Buy: {buy:10s} | Sell: {sell:10s} | Date: {row['effective_date']}")
        else:
            print("No USD rates found")
    
    print()
    print("-" * 80)
    print("📊 CATEGORY DISTRIBUTION")
    print("-" * 80)
    print()
    
    # 3. Category Distribution
    with conn.cursor() as cur:
        cur.execute("""
            SELECT category, COUNT(*) as count
            FROM public.rate_observation
            WHERE collection_date = %s
            GROUP BY category
            ORDER BY count DESC
        """, (today,))
        
        print(f"{'Category':<20} {'Count':>10}")
        print("-" * 32)
        for row in cur.fetchall():
            print(f"{row[0]:<20} {row[1]:>10}")
    
    print()
    print("-" * 80)
    print("🌍 ALL CURRENCIES COLLECTED")
    print("-" * 80)
    print()
    
    # 4. All Currencies
    with conn.cursor() as cur:
        cur.execute("""
            SELECT source_currency_code, COUNT(*) as count
            FROM public.rate_observation
            WHERE collection_date = %s
            GROUP BY source_currency_code
            ORDER BY count DESC
        """, (today,))
        
        currencies = cur.fetchall()
        # Display in columns
        for i in range(0, len(currencies), 4):
            row_data = currencies[i:i+4]
            print("  ".join(f"{code:5s} ({cnt:3d})" for code, cnt in row_data))
    
    print()
    print("-" * 80)
    print("⚠️  VALIDATION STATUS")
    print("-" * 80)
    print()
    
    # 5. Validation Status
    with conn.cursor() as cur:
        cur.execute("""
            SELECT validation_status, COUNT(*) as count
            FROM public.rate_observation
            WHERE collection_date = %s
            GROUP BY validation_status
            ORDER BY count DESC
        """, (today,))
        
        print(f"{'Status':<20} {'Count':>10}")
        print("-" * 32)
        for row in cur.fetchall():
            status_icon = {
                'accepted': '✅',
                'flagged': '⚠️',
                'rejected': '❌'
            }.get(row[0], '❓')
            print(f"{status_icon} {row[0]:<18} {row[1]:>10}")
    
    print()
    print("=" * 80)
    print(f"Analysis complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
