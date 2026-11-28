import os
import decimal
import datetime
import json
import logging
import time
import threading
import psycopg2
from psycopg2 import pool
from flask import Flask, jsonify, request, render_template, abort

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("api")

from adapters.core.dates import business_date_now
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
    get_usd_matrix_data,
    MAJOR_CURRENCIES,
)
from db.repositories.rate_observation_repository import RateObservationRepository

import infrastructure.env

app = Flask(__name__)

DSN = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
if DSN.startswith("postgres://"):
    DSN = DSN.replace("postgres://", "postgresql://", 1)

DB_CONNECT_TIMEOUT = int(os.environ.get("DB_CONNECT_TIMEOUT", "15"))
DB_STATEMENT_TIMEOUT = int(os.environ.get("DB_STATEMENT_TIMEOUT", "10000"))

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")

class ConnectionPoolManager:
    """Manages database connection pool as a singleton with thread-safe access."""
    
    _instance: "ConnectionPoolManager | None" = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._pool = None
        self._dsn = DSN
        self._connect_timeout = DB_CONNECT_TIMEOUT
        self._statement_timeout = DB_STATEMENT_TIMEOUT
        self._initialize_pool()
    
    @classmethod
    def instance(cls) -> "ConnectionPoolManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def _initialize_pool(self):
        """Create the connection pool."""
        try:
            self._pool = self._make_pool()
            logger.info("Database connection pool initialized")
        except Exception as exc:
            logger.error("Failed to create DB connection pool at startup: %s", exc)
            self._pool = None
    
    def _make_pool(self):
        """Factory method to create a new connection pool."""
        kwargs = {
            "minconn": 1,
            "maxconn": 10,
            "dsn": self._dsn,
            "connect_timeout": self._connect_timeout,
        }
        if "-pooler" not in self._dsn:
            kwargs["options"] = f"-c statement_timeout={self._statement_timeout}"
        return pool.ThreadedConnectionPool(**kwargs)
    
    def reset_pool(self):
        """Reset the connection pool (for fork scenarios)."""
        with self._lock:
            if self._pool is not None:
                try:
                    self._pool.closeall()
                except Exception:
                    pass
                self._pool = None
    
    def get_connection(self):
        """Get a connection from the pool, creating pool if needed."""
        for attempt in range(3):
            with self._lock:
                if self._pool is None:
                    try:
                        self._pool = self._make_pool()
                    except Exception as exc:
                        if attempt == 2:
                            logger.error("Failed to lazily create DB connection pool: %s", exc)
                            raise RuntimeError("Database connection pool is not available") from exc
                        time.sleep(0.5 * (attempt + 1))
                        continue
            
            conn = None
            try:
                conn = self._pool.getconn()
                if conn.closed != 0:
                    try:
                        self._pool.putconn(conn, close=True)
                    except Exception:
                        pass
                    conn = None
                    continue
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                return conn
            except Exception as exc:
                if conn is not None:
                    try:
                        self._pool.putconn(conn, close=True)
                    except Exception:
                        pass
                    conn = None
                if attempt == 2:
                    logger.error("Failed to acquire healthy DB connection: %s", exc)
                    raise
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError("Could not acquire database connection")
    
    def return_connection(self, conn, error: bool = False):
        """Return a connection to the pool."""
        if conn is None or self._pool is None:
            return
        try:
            if error or conn.closed != 0:
                self._pool.putconn(conn, close=True)
            else:
                conn.rollback()
                self._pool.putconn(conn)
        except Exception:
            try:
                self._pool.putconn(conn, close=True)
            except Exception:
                pass


# Initialize global pool manager
_pool_manager = ConnectionPoolManager.instance()

# Legacy compatibility functions
def _reset_pool():
    """Legacy function for gunicorn post_fork hook."""
    _pool_manager.reset_pool()

def _conn():
    """Legacy function - get a connection from the pool."""
    return _pool_manager.get_connection()

def _put(conn, error: bool = False):
    """Legacy function - return a connection to the pool."""
    _pool_manager.return_connection(conn, error=error)


PAGE_SIZE = 25


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGINS
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


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
    has_error = False
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.execute("SELECT COUNT(*) FROM rate_observation WHERE is_current = TRUE")
            current_rates = cur.fetchone()[0]
        return jsonify({"status": "ok", "current_rates": current_rates}), 200
    except Exception as exc:
        has_error = True
        logger.warning("Health check warming up: %s", exc)
        return jsonify({"status": "ok", "warning": "warming_up"}), 200
    finally:
        if conn:
            _put(conn, error=has_error)

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
    has_error = False
    try:
        conn = _conn()
        rows = get_available_banks(conn)
    except Exception as exc:
        has_error = True
        logger.error("GET /banks failed: %s", exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn, error=has_error)
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
    has_error = False
    try:
        conn = _conn()
        rows = get_trusted_rates(conn, source_id=source_id, as_of=as_of_date)
    except Exception as exc:
        has_error = True
        logger.error("GET /rates failed: %s", exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn, error=has_error)
    return _json(rows)

@app.get("/rates/by-currency/<code>")
def rates_by_currency(code: str):
    conn = None
    has_error = False
    try:
        conn = _conn()
        rows = get_trusted_rates_by_currency(conn, code.upper())
    except Exception as exc:
        has_error = True
        logger.error("GET /rates/by-currency/%s failed: %s", code, exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn, error=has_error)
    if not rows:
        abort(404)
    return _json(rows)

@app.get("/rates/<int:source_id>")
def rates_for_source(source_id: int):
    conn = None
    has_error = False
    try:
        conn = _conn()
        rows = get_trusted_rates(conn, source_id=source_id)
    except Exception as exc:
        has_error = True
        logger.error("GET /rates/%s failed: %s", source_id, exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn, error=has_error)
    if not rows:
        abort(404)
    return _json(rows)

@app.get("/review")
def review():
    conn = None
    has_error = False
    try:
        conn = _conn()
        pending = get_pending_review_observations(conn)
    except Exception as exc:
        has_error = True
        pending = []
    finally:
        if conn:
            _put(conn, error=has_error)
    return render_template("review.html", pending=pending, now=datetime.datetime.now(datetime.timezone.utc))

@app.post("/review/decide")
def review_decide():
    obs_ids = request.form.getlist("obs_id", type=int)
    decision = request.form.get("decision")
    if not obs_ids or decision not in ("approve", "dismiss"):
        return jsonify({"error": "bad request"}), 400

    conn = None
    has_error = False
    try:
        conn = _conn()
        repo = RateObservationRepository(conn)

        if decision == "approve":
            for oid in obs_ids:
                obs = repo.get_observation_for_review(oid)
                if not obs:
                    continue

                active = repo.get_active_observation(
                    obs['source_id'], obs['source_currency_code'], obs['category_id']
                )

                promote = True
                if active:
                    active_eff = active['effective_date']
                    cand_eff = obs['effective_date']
                    if active_eff is not None and cand_eff is not None and cand_eff < active_eff:
                        promote = False
                    elif active_eff is not None and cand_eff is None:
                        promote = False

                if promote:
                    repo.retire_current_observations(
                        obs['source_id'], obs['source_currency_code'], obs['category_id']
                    )
                repo.approve_observation(oid, promote=promote)
        else:
            repo.dismiss_observations(obs_ids)

        conn.commit()
    except Exception as exc:
        has_error = True
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.error("POST /review/decide failed: %s", exc)
        return jsonify({"error": "internal server error"}), 500
    finally:
        if conn:
            _put(conn, error=has_error)
    return __import__('flask').redirect("/review")

@app.get("/usd")
def usd_matrix():
    category = request.args.get("category", "transactional")
    if category not in ("transactional", "cash"):
        category = "transactional"
    conn = None
    has_error = False
    try:
        conn = _conn()
        rate_rows, run_rows = get_usd_matrix_data(conn, category)
    except Exception as exc:
        has_error = True
        logger.error("GET /usd failed: %s", exc)
        rate_rows, run_rows = [], []
    finally:
        if conn:
            _put(conn, error=has_error)

    today = business_date_now()
    all_dates = [today - datetime.timedelta(days=i) for i in range(31)]

    successful_runs = set()
    for source_id, run_date, had_success in run_rows:
        if had_success:
            successful_runs.add((source_id, run_date))

    rates_by_source = {}
    banks_set = {}
    for source_id, bank_name, bank_code, eff_date, buying, selling in rate_rows:
        if eff_date is None:
            continue
        banks_set[bank_code] = bank_name
        rates_by_source.setdefault(source_id, {})[eff_date] = {
            "code": bank_code,
            "buying": buying,
            "selling": selling,
        }

    matrix = {}
    for source_id, date_rates in rates_by_source.items():
        prev_rate = None
        for d in sorted(all_dates):
            if d in date_rates:
                prev_rate = date_rates[d]
                matrix.setdefault(d, {})[prev_rate["code"]] = {
                    "buying": prev_rate["buying"],
                    "selling": prev_rate["selling"],
                }
            elif prev_rate and (source_id, d) in successful_runs:
                matrix.setdefault(d, {})[prev_rate["code"]] = {
                    "buying": prev_rate["buying"],
                    "selling": prev_rate["selling"],
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
    has_error = False
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
        has_error = True
        logger.error("GET / (view=%s) failed: %s", view, exc)
        rows, currencies, banks, suggestions = [], [], [], {"currencies": [], "banks": []}
        bank_data, matrix, hist_rows, dates = {}, None, [], []
        error = "Failed to load data. Please try again."
    finally:
        if conn:
            _put(conn, error=has_error)

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
