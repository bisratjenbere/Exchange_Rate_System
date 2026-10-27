import os
import decimal
import datetime
import json
import logging
import psycopg2
from psycopg2 import pool
from flask import Flask, jsonify, request, render_template, abort

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("api")

from trusted_view.query import (
    get_trusted_rates,
    get_trusted_rates_by_currency,
    get_best_rates_by_currency,
    get_bank_rates_pivoted,
    get_currency_matrix,
    get_available_currencies,
    get_available_banks,
    get_available_dates,
    get_history_by_currency,
    get_search_suggestions,
    get_pending_review_observations,
    MAJOR_CURRENCIES,
)

app = Flask(__name__)

DSN = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
if DSN.startswith("postgres://"):
    DSN = DSN.replace("postgres://", "postgresql://", 1)

DB_CONNECT_TIMEOUT = int(os.environ.get("DB_CONNECT_TIMEOUT", "5"))
DB_STATEMENT_TIMEOUT = int(os.environ.get("DB_STATEMENT_TIMEOUT", "10000"))

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGINS
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

def _make_pool():
    return pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=DSN,
        connect_timeout=DB_CONNECT_TIMEOUT,
        options=f"-c statement_timeout={DB_STATEMENT_TIMEOUT}",
    )

try:
    _pool = _make_pool()
except Exception as exc:
    logger.error("Failed to create DB connection pool at startup: %s", exc)
    _pool = None

PAGE_SIZE = 25

def _conn():
    if _pool is None:
        raise RuntimeError("Database connection pool is not available")
    return _pool.getconn()

def _put(conn):
    try:
        _pool.putconn(conn)
    except Exception:
        pass

def _serialise(obj):
    if isinstance(obj, decimal.Decimal):
        return str(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(f"Not serialisable: {type(obj)}")

def _json(data):
    return app.response_class(
        json.dumps(data, default=_serialise),
        mimetype="application/json",
    )

@app.get("/health")
def health():
    conn = None
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.execute("SELECT COUNT(*) FROM rate_observation WHERE is_current = TRUE")
            current_rates = cur.fetchone()[0]
        return jsonify({"status": "ok", "current_rates": current_rates})
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        return jsonify({"status": "error"}), 503
    finally:
        if conn:
            _put(conn)

@app.get("/metrics")
def metrics():
    try:
        from infrastructure.metrics import get_metrics_text
        metrics_output = get_metrics_text()
        return app.response_class(
            metrics_output,
            mimetype='text/plain; version=0.0.4'
        )
    except Exception as exc:
        logger.error("Metrics export failed: %s", exc)
        return "# Metrics unavailable\n", 500

@app.get("/banks")
def banks():
    conn = None
    try:
        conn = _conn()
        rows = get_available_banks(conn)
    except Exception as exc:
        logger.error("GET /banks failed: %s", exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn)
    return _json(rows)

@app.get("/rates")
def rates():
    source_id = request.args.get("source_id", type=int)
    as_of = request.args.get("as_of", "").strip()
    as_of_date = None
    if as_of:
        try:
            as_of_date = datetime.date.fromisoformat(as_of)
        except ValueError:
            return jsonify({"error": "invalid as_of date, use YYYY-MM-DD"}), 400
    conn = None
    try:
        conn = _conn()
        rows = get_trusted_rates(conn, source_id=source_id, as_of=as_of_date)
    except Exception as exc:
        logger.error("GET /rates failed: %s", exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn)
    return _json(rows)

@app.get("/rates/by-currency/<code>")
def rates_by_currency(code: str):
    conn = None
    try:
        conn = _conn()
        rows = get_trusted_rates_by_currency(conn, code.upper())
    except Exception as exc:
        logger.error("GET /rates/by-currency/%s failed: %s", code, exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn)
    if not rows:
        abort(404)
    return _json(rows)

@app.get("/rates/<int:source_id>")
def rates_for_source(source_id: int):
    conn = None
    try:
        conn = _conn()
        rows = get_trusted_rates(conn, source_id=source_id)
    except Exception as exc:
        logger.error("GET /rates/%s failed: %s", source_id, exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn)
    if not rows:
        abort(404)
    return _json(rows)

@app.get("/review")
def review():
    conn = None
    try:
        conn = _conn()
        pending = get_pending_review_observations(conn)
    except Exception as exc:
        pending = []
    finally:
        if conn:
            _put(conn)
    return render_template("review.html", pending=pending, now=__import__('datetime').datetime.now(__import__('datetime').timezone.utc))

@app.post("/review/decide")
def review_decide():
    obs_ids = request.form.getlist("obs_id", type=int)
    decision = request.form.get("decision")
    if not obs_ids or decision not in ("approve", "dismiss"):
        return jsonify({"error": "bad request"}), 400

    conn = None
    try:
        conn = _conn()
        with conn.cursor() as cur:
            if decision == "approve":
                for oid in obs_ids:
                    cur.execute("""
                        SELECT source_id, source_currency_code, category_id, effective_date
                        FROM rate_observation WHERE id = %s
                    """, (oid,))
                    cand_row = cur.fetchone()
                    if not cand_row:
                        continue
                    sid, cur_code, cat_id, cand_eff_date = cand_row

                    cur.execute("""
                        SELECT id, effective_date
                        FROM rate_observation
                        WHERE source_id = %s
                          AND source_currency_code = %s
                          AND category_id IS NOT DISTINCT FROM %s
                          AND is_current = TRUE
                        LIMIT 1
                    """, (sid, cur_code, cat_id))
                    active_row = cur.fetchone()

                    promote = True
                    if active_row:
                        active_id, active_eff_date = active_row
                        if active_eff_date is not None and cand_eff_date is not None and cand_eff_date < active_eff_date:
                            promote = False
                        elif active_eff_date is not None and cand_eff_date is None:
                            promote = False

                    if promote:
                        cur.execute("""
                            UPDATE rate_observation
                            SET is_current = FALSE
                            WHERE source_id = %s
                              AND source_currency_code = %s
                              AND category_id IS NOT DISTINCT FROM %s
                              AND is_current = TRUE
                        """, (sid, cur_code, cat_id))
                        cur.execute("""
                            UPDATE rate_observation
                            SET is_current = TRUE, change_review_status = 'new_publication'
                            WHERE id = %s
                        """, (oid,))
                    else:
                        cur.execute("""
                            UPDATE rate_observation
                            SET is_current = FALSE, change_review_status = 'new_publication'
                            WHERE id = %s
                        """, (oid,))
            else:
                cur.execute("""
                    UPDATE rate_observation
                    SET change_review_status = 'dismissed'
                    WHERE id = ANY(%s)
                """, (obs_ids,))
        conn.commit()
    except Exception as exc:
        if conn:
            conn.rollback()
        logger.error("POST /review/decide failed: %s", exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn)
    return __import__('flask').redirect("/review")

@app.get("/usd")
def usd_matrix():
    category = request.args.get("category", "transactional")
    if category not in ("transactional", "cash"):
        category = "transactional"
    conn = None
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (rs.id, o.fetched_at::date)
                    b.name AS bank_name,
                    b.code AS bank_code,
                    o.fetched_at::date AS effective_date,
                    o.buying_rate,
                    o.selling_rate
                FROM rate_observation o
                JOIN rate_source rs ON rs.id = o.source_id
                JOIN bank b ON b.id = rs.bank_id
                JOIN rate_category rc ON rc.id = o.category_id
                WHERE o.validation_status != 'rejected'
                  AND o.identity_status != 'ambiguous'
                  AND o.category_id IS NOT NULL
                  AND rs.is_enabled = TRUE
                  AND o.source_currency_code = 'USD'
                  AND rc.code = %s
                  AND o.fetched_at::date >= CURRENT_DATE - 30
                ORDER BY rs.id, o.fetched_at::date DESC, o.buying_rate DESC NULLS LAST
            """, (category,))
            rows = cur.fetchall()
    except Exception as exc:
        logger.error("GET /usd failed: %s", exc)
        rows = []
    finally:
        if conn:
            _put(conn)

    matrix = {}
    banks_set = {}
    for bank_name, bank_code, eff_date, buying, selling in rows:
        if eff_date is None:
            continue
        banks_set[bank_code] = bank_name
        matrix.setdefault(eff_date, {})[bank_code] = {
            "buying": buying,
            "selling": selling,
        }

    dates = sorted(matrix.keys(), reverse=True)
    banks = sorted(banks_set.keys())

    best_buying_per_date = {}
    for d in dates:
        vals = [matrix[d][b]["buying"] for b in matrix[d] if matrix[d][b]["buying"] is not None]
        if vals:
            best_buying_per_date[d] = max(vals)

    return render_template(
        "usd_matrix.html",
        category=category,
        dates=dates,
        banks=banks,
        bank_names=banks_set,
        matrix=matrix,
        best_buying_per_date=best_buying_per_date,
        now=datetime.datetime.now(datetime.timezone.utc),
    )

@app.get("/")
def ui():
    view      = request.args.get("view", "compare")
    currency  = request.args.get("currency", "USD").upper()
    source_id = request.args.get("source_id", type=int)
    filt      = request.args.get("filter", "major")
    q         = request.args.get("q", "").strip().upper()
    show_all  = request.args.get("show_all", "0") == "1"
    date_str  = request.args.get("date", "").strip()
    rate_type = request.args.get("rate_type", "transactional")
    if rate_type not in ("transactional", "cash"):
        rate_type = "transactional"
    error     = None

    sel_date = None
    if date_str:
        try:
            sel_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            pass

    major_only = (filt == "major")

    conn = None
    try:
        conn = _conn()
        currencies   = get_available_currencies(conn)
        banks        = get_available_banks(conn)
        suggestions  = get_search_suggestions(conn)
        dates = get_available_dates(conn)

        if view == "compare":
            if q and q in currencies:
                currency = q
            rows        = get_best_rates_by_currency(conn, currency, category=rate_type)
            bank_data   = None
            matrix      = None
            hist_rows   = []

        elif view == "history":
            if q and q in currencies:
                currency = q
            hist_rows = get_history_by_currency(conn, currency, sel_date)
            rows, bank_data, matrix = [], None, None

        elif view == "bank":
            if q and not source_id:
                match = next((b for b in banks if q in b["name"].upper()), None)
                if match:
                    source_id = match["id"]
            rows      = []
            hist_rows = []
            bank_data = get_bank_rates_pivoted(conn, source_id) if source_id else {}
            matrix    = None

            if bank_data and bank_data.get("currencies"):
                curs = bank_data["currencies"]
                if major_only:
                    curs = {c: v for c, v in curs.items() if c in MAJOR_CURRENCIES}
                if q and q not in currencies:
                    curs = {c: v for c, v in curs.items() if q in c}
                bank_data["currencies"] = curs

        else:
            rows      = []
            bank_data = None
            hist_rows = []
            matrix    = get_currency_matrix(conn, major_only=major_only)
            if q and matrix:
                matrix["currencies"] = [c for c in matrix["currencies"] if q in c]

    except Exception as exc:
        logger.error("GET / (view=%s) failed: %s", view, exc)
        rows, currencies, banks, suggestions = [], [], [], {"currencies": [], "banks": []}
        bank_data, matrix, hist_rows, dates = {}, None, [], []
        error = "Failed to load data. Please try again."
    finally:
        if conn:
            _put(conn)

    max_buying = None
    if view == "compare" and rows:
        max_buying = max((r["buying_rate"] for r in rows if r["buying_rate"]), default=None)

    total_currencies = len(bank_data.get("currencies", {})) if bank_data else 0
    paginated = not show_all and total_currencies > PAGE_SIZE

    hist_by_date = {}
    for r in hist_rows:
        d = r["effective_date"]
        if d is None:
            continue
        hist_by_date.setdefault(d, []).append(r)
    for d in hist_by_date:
        hist_by_date[d].sort(key=lambda r: r["buying_rate"] or 0, reverse=True)

    return render_template(
        "index.html",
        view=view,
        currency=currency,
        currencies=currencies,
        banks=banks,
        suggestions=suggestions,
        source_id=source_id,
        filt=filt,
        q=q,
        show_all=show_all,
        sel_date=sel_date,
        dates=dates,
        rows=rows,
        bank_data=bank_data,
        matrix=matrix,
        hist_by_date=hist_by_date,
        max_buying=max_buying,
        page_size=PAGE_SIZE,
        paginated=paginated,
        total_currencies=total_currencies,
        error=error,
        rate_type=rate_type,
        now=datetime.datetime.now(datetime.timezone.utc),
        major_currencies=MAJOR_CURRENCIES,
    )

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    app.run(host="0.0.0.0", port=port, debug=False)
