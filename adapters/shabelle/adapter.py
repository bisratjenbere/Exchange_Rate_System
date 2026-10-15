"""
adapters/shabelle/adapter.py — Shabelle Bank (HTML div blocks).

Fetch: GET https://shabellebank.com/

Each div.exchange-block-one contains one currency:
  upper-box: h5 contains "Cash Buying/Selling"  → cash category
  lower-box: h5 contains "Trans Buying/Selling" → transactional category
  Values in buys-box p: "160.8580 164.0752" (space-separated buy sell)

Date from page text: "Applicable on 08-October -2026"

Code normalization:
  usd/USD → USD, Euro/EURO → EUR, UAE → AED

Parse rules:
- "No trade" values → skip.
- Date basis: source_published if date found, else collection_date_fallback.
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "shabelle_html"
SOURCE_URL = "https://shabellebank.com/"

_CODE_MAP = {"usd": "USD", "euro": "EUR", "eur": "EUR", "uae": "AED"}


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")

    effective_date = _parse_date(soup)
    date_basis = "source_published" if effective_date else "collection_date_fallback"

    blocks = soup.find_all("div", class_="exchange-block-one")
    if not blocks:
        return [], ["no_exchange_blocks"]

    records, errors = [], []
    for block in blocks:
        try:
            records.extend(_parse_block(block, effective_date, date_basis))
        except Exception as exc:
            errors.append(f"block:{exc}")
    return records, errors


def _parse_block(block, effective_date, date_basis) -> list:
    records = []
    for box_class, category in [("upper-box", "cash"), ("lower-box", "transactional")]:
        box = block.find("div", class_=box_class)
        if not box:
            continue
        h4 = box.find("h4")
        if not h4:
            continue
        raw_code = h4.get_text(strip=True)
        code = _CODE_MAP.get(raw_code.lower(), raw_code.upper())

        buys_box = box.find("div", class_="buys-box")
        if not buys_box:
            continue
        p = buys_box.find("p")
        if not p:
            continue

        values = p.get_text(strip=True).split()
        if len(values) < 2:
            continue
        buying = _safe_rate(values[0])
        selling = _safe_rate(values[1])
        if buying is None and selling is None:
            continue

        records.append(AdapterRecord(
            source_currency_code=code,
            category=category,
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=f"{values[0]}/{values[1]}",
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=f"{effective_date}:{code}:{category}",
            source_publication_key=str(effective_date) if effective_date else None,
            unit_multiplier=1,
            raw_excerpt={"currency": code, "buying": values[0], "selling": values[1]},
            mapping_notes=[],
        ))
    return records


def _parse_date(soup) -> Optional[date]:
    # "Applicable on 08-October -2026" or "Applicable on 08-October-2026"
    text = soup.get_text(" ")
    m = re.search(r"Applicable\s+on\s+([\d]{1,2})[- ]+(\w+)\s*[-]?\s*(\d{4})", text, re.I)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date()
    except ValueError:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y").date()
        except ValueError:
            return None


def _safe_rate(raw) -> Optional[Decimal]:
    if not raw or str(raw).strip().lower() in ("no trade", "no_trade", "-", ""):
        return None
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


def schema_fingerprint(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    blocks = soup.find_all("div", class_="exchange-block-one")
    codes = []
    for b in blocks:
        h4 = b.find("h4")
        if h4:
            codes.append(h4.get_text(strip=True))
    return hashlib.sha256(str({"blocks": len(blocks), "codes": codes}).encode()).hexdigest()
