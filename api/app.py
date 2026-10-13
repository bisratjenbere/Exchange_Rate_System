"""
api/app.py — read API for trusted exchange rates.

Endpoints (JSON):
  GET /health
  GET /banks
  GET /rates
  GET /rates?source_id=<id>
  GET /rates/<source_id>
  GET /rates/by-currency/<code>

UI:
  GET /   ?view=compare  &currency=USD  &filter=major|all  &q=<search>
          ?view=bank     &source_id=1   &filter=major|all  &q=<search>  &show_all=1
          ?view=all                     &filter=major|all  &q=<search>
"""
import os
import decimal
import datetime
import json
import psycopg2
from flask import Flask, jsonify, request, render_template, abort

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
    MAJOR_CURRENCIES,
)

app = Flask(__name__)

# Handle different DATABASE_URL formats (Render uses postgres://, psycopg2 needs postgresql://)
DSN = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
if DSN.startswith("postgres://"):
    DSN = DSN.replace("postgres://", "postgresql://", 1)

PAGE_SIZE = 25


def _conn():
    return psycopg2.connect(DSN)


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


# ── JSON endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return jsonify({"status": "ok"})
    except Exception as exc:
        return jsonify({"status": "error", "detail": str(exc)}), 503


@app.get("/banks")
def banks():
    try:
        with _conn() as conn:
            rows = get_available_banks(conn)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return _json(rows)


@app.get("/rates")
def rates():
    source_id = request.args.get("source_id", type=int)
    try:
        with _conn() as conn:
            rows = get_trusted_rates(conn, source_id=source_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return _json(rows)


@app.get("/rates/by-currency/<code>")
def rates_by_currency(code: str):
    try:
        with _conn() as conn:
            rows = get_trusted_rates_by_currency(conn, code.upper())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    if not rows:
        abort(404)
    return _json(rows)


@app.get("/rates/<int:source_id>")
def rates_for_source(source_id: int):
    try:
        with _conn() as conn:
            rows = get_trusted_rates(conn, source_id=source_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    if not rows:
        abort(404)
    return _json(rows)


# ── UI ─────────────────────────────────────────────────────────────────────────

@app.get("/")
def ui():
    view      = request.args.get("view", "compare")
    currency  = request.args.get("currency", "USD").upper()
    source_id = request.args.get("source_id", type=int)
    filt      = request.args.get("filter", "major")   # major | all
    q         = request.args.get("q", "").strip().upper()
    show_all  = request.args.get("show_all", "0") == "1"
    date_str  = request.args.get("date", "").strip()
    error     = None

    # parse date param
    sel_date = None
    if date_str:
        try:
            sel_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            pass

    major_only = (filt == "major")

    # resolve search query → redirect intent
    search_redirect = None
    if q:
        # will be resolved in template via datalist; pass through as-is
        search_redirect = q

    try:
        with _conn() as conn:
            currencies   = get_available_currencies(conn)
            banks        = get_available_banks(conn)
            suggestions  = get_search_suggestions(conn)

            dates = get_available_dates(conn)

            if view == "compare":
                if q and q in currencies:
                    currency = q
                rows        = get_best_rates_by_currency(conn, currency)
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

                # apply filter + search to bank currencies
                if bank_data and bank_data.get("currencies"):
                    curs = bank_data["currencies"]
                    if major_only:
                        curs = {c: v for c, v in curs.items() if c in MAJOR_CURRENCIES}
                    if q and q not in currencies:  # q is a currency filter
                        curs = {c: v for c, v in curs.items() if q in c}
                    bank_data["currencies"] = curs

            else:  # all
                rows      = []
                bank_data = None
                hist_rows = []
                matrix    = get_currency_matrix(conn, major_only=major_only)
                if q and matrix:
                    matrix["currencies"] = [c for c in matrix["currencies"] if q in c]

    except Exception as exc:
        rows, currencies, banks, suggestions = [], [], [], {"currencies": [], "banks": []}
        bank_data, matrix, hist_rows, dates = {}, None, [], []
        error = str(exc)

    # bar chart scale for compare view
    max_buying = None
    if view == "compare" and rows:
        max_buying = max((r["buying_rate"] for r in rows if r["buying_rate"]), default=None)

    # soft pagination for by-bank view
    total_currencies = len(bank_data.get("currencies", {})) if bank_data else 0
    paginated = not show_all and total_currencies > PAGE_SIZE

    # group hist_rows by date for template
    hist_by_date = {}
    for r in hist_rows:
        d = r["effective_date"]
        hist_by_date.setdefault(d, []).append(r)

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
        now=datetime.datetime.now(datetime.timezone.utc),
        major_currencies=MAJOR_CURRENCIES,
    )
