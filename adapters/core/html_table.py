"""
HTML Table Adapter - Declarative spec for table-based bank sites.

Design: Header-matched columns (not positional) for resilience.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Mapping

from bs4 import BeautifulSoup

from adapters.core.contract import (
    Adapter, ParseOutcome, ParseContext, RowIssue, IssueCode, Severity
)
from adapters.core.numbers import parse_decimal, scale_per_100_units
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record


@dataclass(frozen=True)
class TableSpec:
    """
    Specification for HTML table parsing.
    
    Attributes:
        key: Adapter key (e.g., "dashen_html")
        url: Bank website URL
        headers: Mapping of logical column → header text variants
                 Example: {"currency": ("currency", "code"), "buy": ("buying", "cash buying")}
        required: Logical columns that must be present
        per_units: Currency-specific unit multipliers (e.g., {"JPY": 100})
        expected_categories: If set, validate these categories exist in tables
    """
    key: str
    url: str
    headers: Mapping[str, tuple[str, ...]]
    required: tuple[str, ...] = ("currency", "buy", "sell")
    per_units: Mapping[str, int] = field(default_factory=dict)
    expected_categories: tuple[str, ...] = ()
    header_row: int = 0  # Which <tr> index contains the column headers


def find_table_by_headers(soup: BeautifulSoup, headers: Mapping[str, tuple[str, ...]], 
                          required: tuple[str, ...],
                          required_header_row: int = 0) -> tuple | None:
    """
    Find first table matching header requirements.
    
    Args:
        soup: BeautifulSoup parsed HTML
        headers: Logical column → header text variants mapping
        required: Required logical columns
    
    Returns:
        (table, column_map, header_cells): If found
        None: If no matching table
    
    Example:
        headers = {"currency": ("currency", "code"), "buy": ("buying",)}
        → Finds table with headers containing "currency" or "code", and "buying"
        → Returns {" currency": 0, "buy": 1}
    """
    for table in soup.find_all("table"):
        all_rows = table.find_all("tr")
        if not all_rows:
            continue

        header_row_idx = required_header_row if required_header_row < len(all_rows) else 0
        header_tr = all_rows[header_row_idx]

        # Extract header cells, normalize to lowercase
        cells = header_tr.find_all(["th", "td"])
        header_texts = [
            " ".join(c.get_text(" ", strip=True).lower().split())
            for c in cells
        ]
        
        # Try to match logical columns to header positions
        column_map = {}
        for logical, variants in headers.items():
            for idx, cell_text in enumerate(header_texts):
                if any(variant.lower() in cell_text for variant in variants):
                    column_map[logical] = idx
                    break
        
        if all(req in column_map for req in required):
            return table, column_map, header_texts, header_row_idx
    
    return None


class HtmlTableAdapter:
    """
    Generic HTML table adapter using declarative spec.
    
    Implements Adapter protocol with header-matched column extraction.
    """
    
    def __init__(self, spec: TableSpec):
        self.spec = spec
        self.key = spec.key
        self.url = spec.url
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse HTML table into records.
        
        Steps:
        1. Find table with matching headers
        2. For each data row:
           a. Extract currency, buy, sell values
           b. Parse as Decimal (ValueError → RowIssue)
           c. Normalize currency
           d. Build record
        3. Sort records by (currency_code, category)
        4. Compute structure hash from header cells
        """
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "empty HTML body")
        
        soup = BeautifulSoup(raw, "lxml")
        found = find_table_by_headers(
            soup, self.spec.headers, self.spec.required, self.spec.header_row
        )
        
        if not found:
            return ParseOutcome.failed(
                IssueCode.NO_TABLE,
                f"no table with headers: {', '.join(self.spec.required)}"
            )
        
        table, col_map, header_cells, header_row_idx = found
        
        records = []
        issues = []
        rows_seen = 0
        
        # Parse data rows — skip everything up to and including the header row
        for row_idx, row in enumerate(table.find_all("tr")[header_row_idx + 1:], start=1):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            
            if not cells or len(cells) <= max(col_map.values()):
                # Empty row or too few cells
                continue

            # Stop at a section sub-header row (first cell is text, not a number or currency)
            # Detected when: first data cell doesn't look like a rate AND second cell is empty/text
            currency_text = cells[col_map["currency"]].strip()
            buy_text = cells[col_map["buy"]].strip()
            if currency_text and not buy_text.replace(".", "").replace(",", "").isdigit():
                from adapters.core.currency import normalize_currency as _nc
                if _nc(currency_text) is None and buy_text == "":
                    # Sub-header row like "Transaction Rates" — stop cash section
                    break
            
            rows_seen += 1
            row_ref = f"row {row_idx}"
            
            # Extract currency
            currency_text = cells[col_map["currency"]]
            currency_code = normalize_currency(currency_text)
            
            if not currency_code:
                issues.append(RowIssue(
                    row_ref, IssueCode.UNKNOWN_CURRENCY,
                    currency_text, Severity.WARNING
                ))
                continue
            
            # Extract rates
            buy = None
            sell = None
            
            try:
                buy_text = cells[col_map["buy"]]
                buy = parse_decimal(buy_text)
            except ValueError as exc:
                issues.append(RowIssue(
                    currency_code, IssueCode.BAD_NUMBER,
                    f"buy: {exc}", Severity.ERROR
                ))
            
            try:
                sell_text = cells[col_map["sell"]]
                sell = parse_decimal(sell_text)
            except ValueError as exc:
                issues.append(RowIssue(
                    currency_code, IssueCode.BAD_NUMBER,
                    f"sell: {exc}", Severity.ERROR
                ))
            
            # Skip row if both rates failed to parse
            if buy is None and sell is None:
                # Both rates missing/invalid - skip this row
                continue
            
            # Validate buy/sell relationship
            if buy is not None and sell is not None and buy > sell:
                issues.append(RowIssue(
                    currency_code, IssueCode.BUY_ABOVE_SELL,
                    f"{buy} > {sell}", Severity.WARNING
                ))
                # Keep the row despite warning
            
            # Apply per-unit scaling if needed
            per_units = self.spec.per_units.get(currency_code, 1)
            if per_units != 1:
                buy = scale_per_100_units(buy, currency_code) if buy else buy
                sell = scale_per_100_units(sell, currency_code) if sell else sell
            
            # Build record
            record = build_record(
                currency_code=currency_code,
                category=ctx.category,
                buying_rate=buy,
                selling_rate=sell,
                ctx=ctx,
                per_units=per_units,
            )
            
            records.append(record)
        
        # Sort for determinism
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        # Compute structure hash (header cells + count)
        structure_hash = _compute_structure_hash(header_cells)
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=rows_seen,
            structure_hash=structure_hash,
        )


def _compute_structure_hash(header_cells: list[str]) -> str:
    """
    Compute structure hash from header cells.
    
    Hash depends ONLY on structure (headers + count), not rate values.
    This ensures rate changes don't trigger schema change alerts.
    """
    structure_text = "|".join(header_cells) + f"#{len(header_cells)}"
    return hashlib.sha256(structure_text.encode()).hexdigest()[:16]
