"""
seed_and_run.py — seed real bank sources from source-register.json and run collection.

Enabled sources: only banks with a working adapter (Waves 1-4).
Skipped: Wave 5 (nonce/JS/DNS), blocked (403), JS-rendered with no adapter.
SSL sources (boa, amhara, hibret): ssl_verify=False per ADR-009.
global adapter_key in register is 'global_html' → maps to adapters.global_.adapter.
"""
import json
import os
import psycopg2
from scheduler.runner import run_all

DSN = os.environ.get("DATABASE_URL", "dbname=exchange_rates")

# adapter_key from register → adapter module directory name
# Only entries with a working adapter directory are included
ADAPTER_KEY_MAP = {
    "cbe_api":        "cbe",
    "adib_api":       "adib",
    "dashen_html":    "dashen",
    "rammis_api":     "rammis",
    "wegagen_api":    "wegagen",
    "cbo_html":       "cbo",
    "hibret_html":    "hibret",
    "amhara_html":    "amhara",
    "boa_html":       "boa",
    "bunna_html":     "bunna",
    "goh_betoch_html":"goh_betoch",
    "nib_html":       "nib",
    "sidama_html":    "sidama",
    "berhan_html":    "berhan",
    "tsehay_html":    "tsehay",
    "dbe_html":       "dbe",
    "siinqee_html":   "siinqee",
    "global_html":    "global_",
    "ahadu_html":     "ahadu",
    "enat_html":      "enat",
    "omo_html":       "omo",
}

# Sources that need ssl_verify=False (ADR-009)
SSL_NO_VERIFY = {"hibret_html", "amhara_html", "boa_html"}

# collection_method string mapping
METHOD_MAP = {
    "api":           "api",
    "html":          "html",
    "ajax_endpoint": "ajax_endpoint",
    "browser":       "browser",
}


def seed(conn):
    with open("docs/register/source-register.json") as f:
        register = json.load(f)

    inserted = 0
    skipped = 0

    with conn.cursor() as cur:
        for bank in register["banks"]:
            if not bank.get("is_active", False):
                skipped += 1
                continue

            # Upsert bank
            cur.execute(
                """INSERT INTO bank (code, name, source_authority, is_active)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (code) DO UPDATE
                     SET name = EXCLUDED.name,
                         source_authority = EXCLUDED.source_authority,
                         is_active = EXCLUDED.is_active
                   RETURNING id""",
                (bank["bank_code"], bank["bank_name"],
                 bank.get("source_authority", "official"),
                 bank.get("is_active", True)),
            )
            bank_id = cur.fetchone()[0]

            for src in bank.get("sources", []):
                adapter_key = src["adapter_key"]
                has_adapter = adapter_key in ADAPTER_KEY_MAP
                is_enabled = has_adapter  # enable only what has a working adapter
                ssl_verify = adapter_key not in SSL_NO_VERIFY
                method = METHOD_MAP.get(src.get("collection_method", "html"), "html")

                cur.execute(
                    """INSERT INTO rate_source
                           (bank_id, source_url, collection_method, adapter_key,
                            verification_status, is_enabled, ssl_verify)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING
                       RETURNING id""",
                    (bank_id, src["source_url"], method, adapter_key,
                     src.get("verification_status", "unverified"),
                     is_enabled, ssl_verify),
                )
                row = cur.fetchone()
                if row:
                    inserted += 1
                    status = "ENABLED" if is_enabled else "disabled"
                    print(f"  {status:8s} {adapter_key}")
                else:
                    skipped += 1

    conn.commit()
    print(f"\nSeeded: {inserted} sources inserted, {skipped} skipped (already exist or inactive).")

    # Disable test fixture sources left over from pytest runs
    with conn.cursor() as cur:
        cur.execute("UPDATE rate_source SET is_enabled = FALSE "
                    "WHERE adapter_key ~ '^(fr|sc|dd|sr)[0-9]+$'")
        if cur.rowcount:
            print(f"Disabled {cur.rowcount} test fixture sources.")

    # Set default_category for Rammis and Wegagen (ADR-010, ADR-011)
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE rate_source SET
                default_category = 'transactional',
                default_category_reason = 'Single buying/selling pair. ADR-010.',
                default_category_set_date = '2026-10-12'
            WHERE adapter_key = 'rammis_api' AND default_category IS NULL""")
        cur.execute("""
            UPDATE rate_source SET
                default_category = 'transactional',
                default_category_reason = 'buying==tra_buying for all records. ADR-011.',
                default_category_set_date = '2026-10-12'
            WHERE adapter_key = 'wegagen_api' AND default_category IS NULL""")
        # ADR-012: single-pair banks with no category label
        for key in ('ahadu_html', 'enat_html', 'dbe_html', 'siinqee_html',
                    'goh_betoch_html', 'global_html'):
            cur.execute("""
                UPDATE rate_source SET
                    default_category = 'transactional',
                    default_category_reason = 'Single unlabeled pair. ADR-012.',
                    default_category_set_date = '2026-10-12'
                WHERE adapter_key = %s AND default_category IS NULL""", (key,))
    conn.commit()


def check(conn):
    """Print current source state without modifying anything."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT rs.id, b.name, rs.adapter_key, rs.is_enabled,
                   rs.ssl_verify, rs.default_category,
                   rs.last_success_at::date,
                   COUNT(o.id) FILTER (WHERE o.is_current AND o.identity_status = 'confirmed'
                                         AND o.validation_status != 'rejected'
                                         AND o.category_id IS NOT NULL) AS trusted
            FROM rate_source rs
            JOIN bank b ON b.id = rs.bank_id
            LEFT JOIN rate_observation o ON o.source_id = rs.id
            WHERE rs.adapter_key !~ '^(fr|sc|dd|sr)[0-9]+$'
            GROUP BY rs.id, b.name, rs.adapter_key, rs.is_enabled,
                     rs.ssl_verify, rs.default_category, rs.last_success_at
            ORDER BY rs.is_enabled DESC, rs.id
        """)
        rows = cur.fetchall()

    print(f"{'ID':>3}  {'adapter_key':<20} {'enabled':>7} {'ssl':>5} "
          f"{'category':<14} {'last_ok':<12} {'trusted':>7}  bank")
    print("-" * 90)
    for r in rows:
        sid, bank, key, enabled, ssl, cat, last_ok, trusted = r
        print(f"{sid:>3}  {key:<20} {'YES' if enabled else 'no':>7} "
              f"{'yes' if ssl else 'NO':>5} {(cat or '-'):<14} "
              f"{str(last_ok or '-'):<12} {trusted:>7}  {bank}")
    print(f"\n{sum(1 for r in rows if r[3])} enabled, "
          f"{sum(r[7] for r in rows)} total trusted rates")


def main():
    import sys
    check_only = "--check" in sys.argv

    conn = psycopg2.connect(DSN)

    if check_only:
        print("=== Source state (read-only) ===")
        check(conn)
        conn.close()
        return

    print("=== Seeding sources ===")
    seed(conn)

    print("\n=== Source state ===")
    check(conn)

    print("\n=== Running collection ===")
    results = run_all(conn)

    print("\n=== Results ===")
    for r in results:
        if r["status"] in ("success", "partial_success"):
            print(f"  OK  {r['source_id']:3d} {r['status']:16s} "
                  f"accepted={r.get('accepted',0)} flagged={r.get('flagged',0)} "
                  f"rejected={r.get('rejected',0)} dupes={r.get('duplicates',0)}")
        else:
            print(f"  ERR {r['source_id']:3d} {r.get('status','?'):16s} "
                  f"{r.get('error_code','?')}: {str(r.get('detail',''))[:80]}")

    conn.close()


if __name__ == "__main__":
    main()
