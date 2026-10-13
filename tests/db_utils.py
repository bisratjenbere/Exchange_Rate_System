"""Shared test database utilities."""
import os
import psycopg2

DB_DSN = os.environ.get(
    "TEST_DB_DSN",
    "dbname=exchange_rates_test"
)


def get_conn():
    return psycopg2.connect(DB_DSN)


def apply_migrations(conn):
    """Apply all migrations in order."""
    import glob, re
    files = sorted(glob.glob("db/migrations/*.sql"))
    with conn.cursor() as cur:
        for path in files:
            with open(path) as f:
                cur.execute(f.read())
    conn.commit()


def reset_schema(conn):
    """Drop and recreate public schema — test isolation."""
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    conn.commit()
