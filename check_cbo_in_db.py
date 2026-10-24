#!/usr/bin/env python3
"""Check CBO data in database and trusted view."""

import psycopg2
import os

# Get database URL from environment
db_url = os.getenv("DATABASE_URL", "dbname=exchange_rates")

conn = psycopg2.connect(db_url)
cur = conn.cursor()

print("=== CBO IN RATE_SOURCE TABLE ===")
cur.execute("""
    SELECT rs.id, rs.adapter_key, b.name, rs.is_enabled, rs.last_success_at
    FROM rate_source rs
    JOIN bank b ON rs.bank_id = b.id
    WHERE rs.adapter_key = 'cbo_html' OR b.name ILIKE '%cooperative%oromia%'
""")
for row in cur.fetchall():
    print(f"ID: {row[0]} | Key: {row[1]} | Name: {row[2]} | Enabled: {row[3]} | Last Success: {row[4]}")

print("\n=== CBO OBSERVATIONS (OCT 20-22, USD ONLY) ===")
cur.execute("""
    SELECT ro.effective_date, ro.currency, ro.category, 
           ro.buying_rate, ro.selling_rate, ro.is_current,
           b.name
    FROM rate_observation ro
    JOIN rate_source rs ON ro.source_id = rs.id
    JOIN bank b ON rs.bank_id = b.id
    WHERE rs.adapter_key = 'cbo_html'
      AND ro.effective_date >= '2026-10-20'
      AND ro.currency = 'USD'
    ORDER BY ro.effective_date DESC, ro.category
""")
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"{row[0]} | {row[1]} {row[2]:15} | Buy: {row[3]:>10} Sell: {row[4]:>10} | Current: {row[5]} | {row[6]}")
else:
    print("No USD observations found for CBO!")

print("\n=== TRUSTED VIEW FOR CBO (OCT 22, USD TRANSACTIONAL) ===")
cur.execute("""
    SELECT bank_name, currency, category, buying_rate, selling_rate, effective_date
    FROM trusted_current_rates
    WHERE bank_name ILIKE '%cooperative%oromia%'
      AND currency = 'USD'
      AND category = 'transactional'
      AND effective_date = '2026-10-22'
""")
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"{row[0]} | {row[1]} {row[2]} | Buy: {row[3]} Sell: {row[4]} | Date: {row[5]}")
else:
    print("❌ CBO NOT FOUND in trusted view for Oct 22 USD transactional!")

conn.close()
