import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional, List

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

@dataclass
class ParseResult:
    records: List[AdapterRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def is_success(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

class BankAdapter(ABC):

    @abstractmethod
    def parse(self, raw_content: str, **options) -> ParseResult:
        pass

    @abstractmethod
    def get_source_url(self) -> str:
        pass

    @abstractmethod
    def get_adapter_key(self) -> str:
        pass

    def schema_fingerprint(self, raw_content: str) -> str:
        return hashlib.sha256(b"generic:no_fingerprint").hexdigest()

    def requires_category(self) -> bool:
        return False

    @staticmethod
    def _safe_rate(raw) -> Optional[Decimal]:
        try:
            return normalize_rate(raw)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_iso_date(date_str: str) -> Optional[date]:
        try:
            return date.fromisoformat(date_str.strip())
        except (ValueError, AttributeError, TypeError):
            return None

    @staticmethod
    def _rate_text(buying_raw, selling_raw) -> str:
        return f"{buying_raw}/{selling_raw}"

class JSONAdapter(BankAdapter):

    def parse(self, raw_content: str, **options) -> ParseResult:
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            result = ParseResult()
            result.add_error(f"JSON parse error: {exc}")
            return result

        return self._process_data(data, **options)

    @abstractmethod
    def _process_data(self, data, **options) -> ParseResult:
        pass

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            data = json.loads(raw_content)
            if isinstance(data, dict):
                keys = sorted(data.keys())
                payload = json.dumps(keys, separators=(",", ":"))
            elif isinstance(data, list) and data:
                keys = sorted(data[0].keys()) if isinstance(data[0], dict) else []
                payload = json.dumps(keys, separators=(",", ":"))
            else:
                payload = f"json:{type(data).__name__}"
            return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            adapter_key = self.get_adapter_key()
            return hashlib.sha256(f"{adapter_key}:unparseable".encode()).hexdigest()

class HTMLTableAdapter(BankAdapter):

    def parse(self, raw_content: str, **options) -> ParseResult:
        soup = BeautifulSoup(raw_content, "html.parser")
        tables, strategy_used = self._find_tables_resilient(soup)

        if not tables:
            result = ParseResult()
            result.add_error("No tables found in HTML (tried all strategies)")
            return result

        if strategy_used != "exact":
            import logging
            logging.info(f"{self.get_adapter_key()}: Found tables using '{strategy_used}' strategy")

        return self._process_tables(soup, tables, **options)

    def _find_tables_resilient(self, soup: BeautifulSoup) -> tuple:
        tables = soup.find_all("table")
        if tables:
            return tables, "exact"

        tables = self._find_tables_fuzzy_selectors(soup)
        if tables:
            return tables, "fuzzy_class"

        tables = self._find_div_based_tables(soup)
        if tables:
            return tables, "div_fallback"

        return [], "none"

    def _find_tables_fuzzy_selectors(self, soup: BeautifulSoup) -> list:
        import re

        patterns = [
            re.compile(r"rate.*table", re.I),
            re.compile(r"exchange.*", re.I),
            re.compile(r".*rate.*", re.I),
            re.compile(r"forex.*", re.I),
            re.compile(r"currency.*", re.I),
        ]

        for pattern in patterns:
            tables = soup.find_all("table", class_=pattern)
            if tables:
                return tables

            divs = soup.find_all("div", class_=pattern)
            for div in divs:
                tables = div.find_all("table")
                if tables:
                    return tables

        return []

    def _find_div_based_tables(self, soup: BeautifulSoup) -> list:
        return []

    def extract_table_category(self, table, soup: Optional[BeautifulSoup] = None) -> str:
        from pipeline.category_normalizer import normalize_category

        for row in table.find_all("tr")[:3]:
            for cell in row.find_all(["th", "td"]):
                txt = cell.get_text(" ", strip=True)
                if txt:
                    cat = normalize_category(txt)
                    if cat != "UNKNOWN":
                        return cat

        for row in table.find_all("tr")[:3]:
            row_txt = row.get_text(" ", strip=True)
            cat = normalize_category(row_txt)
            if cat != "UNKNOWN":
                return cat

        caption = table.find("caption")
        if caption:
            cat = normalize_category(caption.get_text(" ", strip=True))
            if cat != "UNKNOWN":
                return cat

        curr = table
        for _ in range(5):
            prev = curr.find_previous_sibling()
            if prev:
                if prev.name == "table":
                    break
                curr = prev
                txt = prev.get_text(" ", strip=True)
                cat = normalize_category(txt)
                if cat != "UNKNOWN":
                    return cat
            else:
                curr = curr.parent
                if not curr or curr == soup or getattr(curr, "name", None) in ["body", "html", "[document]"]:
                    break
                prev_parent = curr.find_previous_sibling()
                if prev_parent and prev_parent.name != "table":
                    txt = prev_parent.get_text(" ", strip=True)
                    cat = normalize_category(txt)
                    if cat != "UNKNOWN":
                        return cat

        prev_elem = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6", "caption", "table"])
        if prev_elem and prev_elem.name != "table":
            cat = normalize_category(prev_elem.get_text(" ", strip=True))
            if cat != "UNKNOWN":
                return cat

        return "UNKNOWN"

    @abstractmethod
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        pass

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            soup = BeautifulSoup(raw_content, "html.parser")
            tables = soup.find_all("table")

            headers = []
            for table in tables:
                rows = table.find_all("tr")
                if rows:
                    header_cells = rows[0].find_all(["th", "td"])
                    header_text = [c.get_text(strip=True) for c in header_cells]
                    headers.append(header_text)

            sig = {"table_count": len(tables), "headers": headers}
            payload = json.dumps(sig, separators=(",", ":"))
            return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            adapter_key = self.get_adapter_key()
            return hashlib.sha256(f"{adapter_key}:unparseable".encode()).hexdigest()

class HTMLTextAdapter(BankAdapter):

    def parse(self, raw_content: str, **options) -> ParseResult:
        soup = BeautifulSoup(raw_content, "html.parser")
        text = " ".join(soup.get_text(" ", strip=True).split())

        return self._extract_from_text(text, soup, **options)

    @abstractmethod
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        pass
