import os
import sys
import psycopg2

def init_db(dsn=None):
    if dsn is None:
        dsn = os.environ.get('DATABASE_URL', 'dbname=exchange_rates')
    if dsn.startswith('postgres://'):
        dsn = dsn.replace('postgres://', 'postgresql://', 1)

    conn = psycopg2.connect(dsn)
    conn.autocommit = False

    migrations = [
        'db/migrations/001_initial_schema.sql',
        'db/migrations/002_add_failure_tracking.sql',
        'db/migrations/003_fallback_provenance_and_dedup_metrics.sql',
        'db/migrations/004_enforce_single_current_observation.sql',
        'db/migrations/005_consolidate_addis_bank_into_adib.sql',
    ]

    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version VARCHAR(100) PRIMARY KEY, "
                "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            conn.commit()

            cur.execute("SELECT to_regclass('public.bank')")
            bank_exists = cur.fetchone()[0] is not None

            cur.execute("SELECT version FROM schema_migrations")
            applied = {row[0] for row in cur.fetchall()}

            if bank_exists and not applied:
                for mig in migrations:
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
                        (os.path.basename(mig),)
                    )
                conn.commit()
                applied = {os.path.basename(mig) for mig in migrations}

            for migration_file in migrations:
                base_name = os.path.basename(migration_file)
                if base_name in applied:
                    continue
                if not os.path.exists(migration_file):
                    continue
                with open(migration_file, 'r', encoding='utf-8') as f:
                    sql = f.read()
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (base_name,))
                conn.commit()
                print(f"Applied migration: {base_name}")

            seed_file = 'db/seeds/001_seed_banks_and_sources.sql'
            if os.path.exists(seed_file):
                with open(seed_file, 'r', encoding='utf-8') as f:
                    sql = f.read()
                cur.execute(sql)
                conn.commit()
                print(f"Applied seed: {seed_file}")

            cur.execute("SELECT COUNT(*) FROM bank")
            bank_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM rate_source WHERE is_enabled = TRUE")
            source_count = cur.fetchone()[0]
            print(f"Database initialized successfully: {bank_count} banks, {source_count} active sources.")
    except Exception as exc:
        conn.rollback()
        print(f"Database initialization failed: {exc}", file=sys.stderr)
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    target_dsn = sys.argv[1] if len(sys.argv) > 1 else None
    init_db(target_dsn)
