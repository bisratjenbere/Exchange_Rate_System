"""Tests for HtmlTableAdapter and TableSpec."""

import pytest
from decimal import Decimal
from datetime import date

from adapters.core.html_table import HtmlTableAdapter, TableSpec, find_table_by_headers
from adapters.core.contract import ParseContext, IssueCode, Severity
from bs4 import BeautifulSoup


def make_simple_table(headers: list[str], rows: list[list[str]]) -> str:
    """Helper to create simple HTML table."""
    html = "<html><body><table>"
    html += "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
    for row in rows:
        html += "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
    html += "</table></body></html>"
    return html


class TestFindTableByHeaders:
    """Test find_table_by_headers() function."""
    
    def test_finds_table_with_matching_headers(self):
        """Find table when headers match."""
        html = make_simple_table(
            ["Currency", "Buying", "Selling"],
            [["USD", "3.5", "3.6"]]
        )
        soup = BeautifulSoup(html, "lxml")
        
        headers = {
            "currency": ("currency",),
            "buy": ("buying",),
            "sell": ("selling",),
        }
        
        result = find_table_by_headers(soup, headers, ("currency", "buy", "sell"))
        
        assert result is not None
        table, col_map, header_cells = result
        assert col_map["currency"] == 0
        assert col_map["buy"] == 1
        assert col_map["sell"] == 2
    
    def test_case_insensitive_matching(self):
        """Header matching is case-insensitive."""
        html = make_simple_table(
            ["CURRENCY", "BUYING", "SELLING"],
            [["USD", "3.5", "3.6"]]
        )
        soup = BeautifulSoup(html, "lxml")
        
        headers = {
            "currency": ("currency",),
            "buy": ("buying",),
            "sell": ("selling",),
        }
        
        result = find_table_by_headers(soup, headers, ("currency", "buy", "sell"))
        assert result is not None
    
    def test_substring_matching(self):
        """Headers match by substring."""
        html = make_simple_table(
            ["Currency Code", "Cash Buying", "Cash Selling"],
            [["USD", "3.5", "3.6"]]
        )
        soup = BeautifulSoup(html, "lxml")
        
        headers = {
            "currency": ("currency",),
            "buy": ("buying",),
            "sell": ("selling",),
        }
        
        result = find_table_by_headers(soup, headers, ("currency", "buy", "sell"))
        assert result is not None
    
    def test_returns_none_when_missing_required(self):
        """Returns None when required column missing."""
        html = make_simple_table(
            ["Currency", "Buying"],  # Missing "Selling"
            [["USD", "3.5"]]
        )
        soup = BeautifulSoup(html, "lxml")
        
        headers = {
            "currency": ("currency",),
            "buy": ("buying",),
            "sell": ("selling",),
        }
        
        result = find_table_by_headers(soup, headers, ("currency", "buy", "sell"))
        assert result is None


class TestHtmlTableAdapter:
    """Test HtmlTableAdapter with TableSpec."""
    
    def test_simple_table_parsing(self):
        """Parse simple table with 2 currencies."""
        spec = TableSpec(
            key="test",
            url="http://test",
            headers={
                "currency": ("currency",),
                "buy": ("buying",),
                "sell": ("selling",),
            }
        )
        
        adapter = HtmlTableAdapter(spec)
        html = make_simple_table(
            ["Currency", "Buying", "Selling"],
            [
                ["USD", "3.5", "3.6"],
                ["EUR", "4.0", "4.1"],
            ]
        )
        
        ctx = ParseContext(category="cash", collection_date=date(2024, 1, 15), source_id=1)
        outcome = adapter.parse(html, ctx)
        
        assert len(outcome.records) == 2
        assert outcome.error_count == 0
        assert outcome.rows_seen == 2
        
        # First record
        assert outcome.records[0].source_currency_code == "EUR"  # Sorted alphabetically
        assert outcome.records[0].buying_rate == Decimal("4.0")
        assert outcome.records[0].selling_rate == Decimal("4.1")
        assert outcome.records[0].category == "cash"
    
    def test_empty_payload_returns_failed(self):
        """Empty HTML returns failed outcome."""
        spec = TableSpec(key="test", url="http://test", headers={"currency": ("currency",)})
        adapter = HtmlTableAdapter(spec)
        
        ctx = ParseContext(category="cash", collection_date=date.today(), source_id=1)
        outcome = adapter.parse("", ctx)
        
        assert len(outcome.records) == 0
        assert outcome.error_count == 1
        assert outcome.issues[0].code == IssueCode.EMPTY_PAYLOAD
    
    def test_no_table_returns_failed(self):
        """HTML without table returns failed outcome."""
        spec = TableSpec(
            key="test", url="http://test",
            headers={"currency": ("currency",), "buy": ("buying",), "sell": ("selling",)}
        )
        adapter = HtmlTableAdapter(spec)
        
        html = "<html><body><p>No table here</p></body></html>"
        ctx = ParseContext(category="cash", collection_date=date.today(), source_id=1)
        outcome = adapter.parse(html, ctx)
        
        assert len(outcome.records) == 0
        assert outcome.error_count == 1
        assert outcome.issues[0].code == IssueCode.NO_TABLE
    
    def test_bad_number_creates_error_issue(self):
        """Non-numeric junk creates ERROR issue. Row kept if other rate valid."""
        spec = TableSpec(
            key="test", url="http://test",
            headers={"currency": ("currency",), "buy": ("buying",), "sell": ("selling",)}
        )
        adapter = HtmlTableAdapter(spec)
        
        html = make_simple_table(
            ["Currency", "Buying", "Selling"],
            [
                ["USD", "junk", "3.6"],  # Bad buy, valid sell → ROW KEPT
                ["EUR", "4.0", "4.1"],    # Good row
            ]
        )
        
        ctx = ParseContext(category="cash", collection_date=date.today(), source_id=1)
        outcome = adapter.parse(html, ctx)
        
        # Both rows kept (USD with buy=None, EUR with both rates)
        assert len(outcome.records) == 2
        assert outcome.error_count == 1  # Error logged for bad buy
        assert outcome.rows_seen == 2
        assert outcome.issues[0].code == IssueCode.BAD_NUMBER
        assert outcome.issues[0].row_ref == "USD"
        
        # USD record has buy=None, sell=3.6
        usd_rec = [r for r in outcome.records if r.source_currency_code == "USD"][0]
        assert usd_rec.buying_rate is None
        assert usd_rec.selling_rate == Decimal("3.6")
    
    def test_both_rates_bad_skips_row(self):
        """Row skipped if BOTH rates invalid."""
        spec = TableSpec(
            key="test", url="http://test",
            headers={"currency": ("currency",), "buy": ("buying",), "sell": ("selling",)}
        )
        adapter = HtmlTableAdapter(spec)
        
        html = make_simple_table(
            ["Currency", "Buying", "Selling"],
            [
                ["USD", "junk1", "junk2"],  # Both rates bad → SKIPPED
                ["EUR", "4.0", "4.1"],       # Good row
            ]
        )
        
        ctx = ParseContext(category="cash", collection_date=date.today(), source_id=1)
        outcome = adapter.parse(html, ctx)
        
        # Only EUR kept (USD skipped)
        assert len(outcome.records) == 1
        assert outcome.error_count == 2  # Two errors logged
        assert outcome.rows_seen == 2
    
    def test_unknown_currency_creates_warning(self):
        """Unknown currency creates WARNING and skips row."""
        spec = TableSpec(
            key="test", url="http://test",
            headers={"currency": ("currency",), "buy": ("buying",), "sell": ("selling",)}
        )
        adapter = HtmlTableAdapter(spec)
        
        html = make_simple_table(
            ["Currency", "Buying", "Selling"],
            [
                ["JUNK123", "3.5", "3.6"],  # Unknown currency
                ["USD", "3.5", "3.6"],       # Good row
            ]
        )
        
        ctx = ParseContext(category="cash", collection_date=date.today(), source_id=1)
        outcome = adapter.parse(html, ctx)
        
        assert len(outcome.records) == 1  # Only USD
        assert outcome.warning_count == 1
        assert outcome.issues[0].code == IssueCode.UNKNOWN_CURRENCY
        assert outcome.issues[0].severity == Severity.WARNING
    
    def test_buy_above_sell_creates_warning_but_keeps_row(self):
        """Buy > sell creates WARNING but row is kept."""
        spec = TableSpec(
            key="test", url="http://test",
            headers={"currency": ("currency",), "buy": ("buying",), "sell": ("selling",)}
        )
        adapter = HtmlTableAdapter(spec)
        
        html = make_simple_table(
            ["Currency", "Buying", "Selling"],
            [["USD", "3.6", "3.5"]],  # Buy > sell (suspicious)
        )
        
        ctx = ParseContext(category="cash", collection_date=date.today(), source_id=1)
        outcome = adapter.parse(html, ctx)
        
        assert len(outcome.records) == 1  # Row kept despite warning
        assert outcome.warning_count == 1
        assert outcome.issues[0].code == IssueCode.BUY_ABOVE_SELL
        assert outcome.issues[0].severity == Severity.WARNING
    
    def test_structure_hash_stable_across_rate_changes(self):
        """Structure hash doesn't change when only rates change."""
        spec = TableSpec(
            key="test", url="http://test",
            headers={"currency": ("currency",), "buy": ("buying",), "sell": ("selling",)}
        )
        adapter = HtmlTableAdapter(spec)
        
        html1 = make_simple_table(["Currency", "Buying", "Selling"], [["USD", "3.5", "3.6"]])
        html2 = make_simple_table(["Currency", "Buying", "Selling"], [["USD", "3.7", "3.8"]])
        
        ctx = ParseContext(category="cash", collection_date=date.today(), source_id=1)
        
        outcome1 = adapter.parse(html1, ctx)
        outcome2 = adapter.parse(html2, ctx)
        
        # Structure hash should be SAME (only rates changed)
        assert outcome1.structure_hash == outcome2.structure_hash
    
    def test_structure_hash_changes_when_headers_change(self):
        """Structure hash changes when headers change."""
        spec = TableSpec(
            key="test", url="http://test",
            headers={"currency": ("currency",), "buy": ("buying",), "sell": ("selling",)}
        )
        adapter = HtmlTableAdapter(spec)
        
        html1 = make_simple_table(["Currency", "Buying", "Selling"], [["USD", "3.5", "3.6"]])
        html2 = make_simple_table(["Currency", "Buying", "Selling", "Mid"], [["USD", "3.5", "3.6", "3.55"]])
        
        ctx = ParseContext(category="cash", collection_date=date.today(), source_id=1)
        
        outcome1 = adapter.parse(html1, ctx)
        outcome2 = adapter.parse(html2, ctx)
        
        # Structure hash should be DIFFERENT (column added)
        assert outcome1.structure_hash != outcome2.structure_hash
