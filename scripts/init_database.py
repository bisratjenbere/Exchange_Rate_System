#!/usr/bin/env python3
"""
Initialize database on first deploy.
Run this manually after first deployment:
  1. Go to Render Dashboard → exchange-rates-api → Shell
  2. Run: python3 scripts/init_database.py
"""
import os
import sys
import psycopg2

DSN = os.environ.get("DATABASE_URL")

# Handle Render's postgres:// format
if DSN and DSN.startswith("postgres://"):
    DSN = DSN.replace("postgres://", "postgresql://", 1)

if not DSN:
    print("ERROR: DATABASE_URL environment variable not set")
    print("This script must be run in the deployment environment with DATABASE_URL configured")
    sys.exit(1)

print("=== Database Initialization ===\n")
print(f"Connecting to database...")

try:
    conn = psycopg2.connect(DSN)
    print("✓ Connected successfully\n")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    sys.exit(1)

# Run migration
print("Step 1: Running migration 001_initial_schema.sql...")
try:
    with open("db/migrations/001_initial_schema.sql") as f:
        sql = f.read()
    
    with conn.cursor() as cur:
        cur.execute(sql)
    
    conn.commit()
    print("✓ Schema created successfully\n")
except Exception as e:
    conn.rollback()
    print(f"❌ Migration failed: {e}")
    sys.exit(1)

# Seed sources
print("Step 2: Seeding sources from register...")
try:
    # Import here to avoid issues if modules not yet in path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from seed_and_run import seed
    
    seed(conn)
    print("✓ Sources seeded\n")
except Exception as e:
    conn.rollback()
    print(f"❌ Seeding failed: {e}")
    print(f"   You may need to run: python3 seed_and_run.py manually")
    sys.exit(1)

conn.close()

print("=" * 50)
print("✅ Database initialization complete!")
print("=" * 50)
print("\nNext steps:")
print("1. Check /health endpoint to verify API is running")
print("2. Check /rates endpoint to see initial data")
print("3. Monitor cron job logs for scheduled collections")
print("4. Set up uptime monitoring (UptimeRobot, etc.)")
