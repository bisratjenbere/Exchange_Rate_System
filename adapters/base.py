"""
adapters/base.py — Base classes for bank adapters.

Provides type-specific base classes that eliminate code duplication:
- BankAdapter: Abstract base class with common interface
- JSONAdapter: For JSON API adapters
- HTMLTableAdapter: For HTML table-based adapters  
- HTMLTextAdapter: For text extraction adapters
- ParseResult: Standard result container with error handling

All base classes provide:
- Standardized parse() interface
- Default schema_fingerprint() implementations
- Common helper methods for rate/date parsing
- Error handling and reporting
"""
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
    """
    Standard result container for adapter parsing.
    
    Attributes:
        records: List of successfully parsed AdapterRecords
        errors: List of error messages (strings)
        warnings: List of warning messages (strings)
    """
    records: List[AdapterRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def is_success(self) -> bool:
        """Returns True if no errors occurred."""
        return len(self.errors) == 0
    
    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
    
    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)


class BankAdapter(ABC):
    """
    Abstract base class for all bank adapters.
    
    Provides standard interface that all adapters must implement:
    - parse(): Convert raw content to AdapterRecords
    - get_source_url(): Return the source URL
    - get_adapter_key(): Return unique adapter identifier
    - schema_fingerprint(): Generate structural signature
    - requires_category(): Whether adapter needs category parameter
    
    Also provides helper methods for common operations.
    """
    
    @abstractmethod
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        Parse raw content into AdapterRecords.
        
        Args:
            raw_content: Raw HTML or JSON string from source
            **options: Additional parsing options (e.g., category)
            
        Returns:
            ParseResult containing records, errors, and warnings
        """
        pass
    
    @abstractmethod
    def get_source_url(self) -> str:
        """Return the source URL for this adapter."""
        pass
    
    @abstractmethod
    def get_adapter_key(self) -> str:
        """Return the unique adapter key identifier."""
        pass
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """
        Generate a deterministic hash of the content structure.
        
        Override this method to provide adapter-specific fingerprinting.
        Default implementation returns a generic hash.
        
        Args:
            raw_content: Raw HTML or JSON string from source
            
        Returns:
            SHA256 hex digest of structural signature
        """
        return hashlib.sha256(b"generic:no_fingerprint").hexdigest()
    
    def requires_category(self) -> bool:
        """
        Whether this adapter requires a category parameter.
        
        Returns:
            True if parse() requires category option, False otherwise
        """
        return False
    
    # Helper methods for common operations
    
    @staticmethod
    def _safe_rate(raw) -> Optional[Decimal]:
        """
        Safely convert raw value to normalized Decimal rate.
        
        Args:
            raw: Raw rate value (string, number, etc.)
            
        Returns:
            Normalized Decimal rate or None if conversion fails
        """
        try:
            return normalize_rate(raw)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _parse_iso_date(date_str: str) -> Optional[date]:
        """
        Parse ISO format date string (YYYY-MM-DD).
        
        Args:
            date_str: Date string in ISO format
            
        Returns:
            date object or None if parsing fails
        """
        try:
            return date.fromisoformat(date_str.strip())
        except (ValueError, AttributeError, TypeError):
            return None
    
    @staticmethod
    def _rate_text(buying_raw, selling_raw) -> str:
        """
        Format buying/selling rates as text for source_rate_text field.
        
        Args:
            buying_raw: Raw buying rate value
            selling_raw: Raw selling rate value
            
        Returns:
            Formatted string like "1.23/4.56"
        """
        return f"{buying_raw}/{selling_raw}"


class JSONAdapter(BankAdapter):
    """
    Base class for JSON API adapters.
    
    Handles JSON parsing and provides default schema fingerprinting.
    Subclasses must implement _process_data() to extract records from parsed JSON.
    
    Example:
        class CBEAdapter(JSONAdapter):
            def _process_data(self, data: any) -> ParseResult:
                result = ParseResult()
                # Extract records from data
                return result
            
            def get_source_url(self) -> str:
                return "https://api.example.com/rates"
            
            def get_adapter_key(self) -> str:
                return "example_api"
    """
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        Parse JSON content and delegate to _process_data().
        
        Args:
            raw_content: Raw JSON string
            **options: Additional options passed to _process_data()
            
        Returns:
            ParseResult from _process_data() or error result if JSON invalid
        """
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            result = ParseResult()
            result.add_error(f"JSON parse error: {exc}")
            return result
        
        return self._process_data(data, **options)
    
    @abstractmethod
    def _process_data(self, data, **options) -> ParseResult:
        """
        Extract AdapterRecords from parsed JSON data.
        
        Args:
            data: Parsed JSON data (dict, list, etc.)
            **options: Additional parsing options
            
        Returns:
            ParseResult containing extracted records and any errors
        """
        pass
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """
        Default JSON fingerprinting: hash top-level keys.
        
        Override for more sophisticated fingerprinting.
        
        Args:
            raw_content: Raw JSON string
            
        Returns:
            SHA256 hex digest of top-level structure
        """
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
    """
    Base class for HTML table-based adapters.
    
    Handles HTML parsing, table extraction, and provides default fingerprinting.
    Subclasses must implement _process_tables() to extract records from tables.
    
    RESILIENCE FEATURES:
    - Multi-strategy table detection (exact → fuzzy → any table)
    - Fuzzy CSS selector matching for class name changes
    - Automatic fallback when exact selectors fail
    
    Example:
        class DBEAdapter(HTMLTableAdapter):
            def _process_tables(self, soup: BeautifulSoup, tables: list) -> ParseResult:
                result = ParseResult()
                # Extract records from tables
                return result
            
            def get_source_url(self) -> str:
                return "https://example.com/rates"
            
            def get_adapter_key(self) -> str:
                return "example_html"
    """
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        Parse HTML content, extract tables using multi-strategy approach.
        
        Strategies (in order):
        1. Find all <table> elements (exact)
        2. Find tables with rate-related CSS classes (fuzzy)
        3. Find any table elements (fallback)
        4. Report error if no tables found
        
        Args:
            raw_content: Raw HTML string
            **options: Additional options passed to _process_tables()
            
        Returns:
            ParseResult from _process_tables() or error if no tables found
        """
        soup = BeautifulSoup(raw_content, "html.parser")
        tables, strategy_used = self._find_tables_resilient(soup)
        
        if not tables:
            result = ParseResult()
            result.add_error("No tables found in HTML (tried all strategies)")
            return result
        
        # Log which strategy succeeded (for monitoring)
        if strategy_used != "exact":
            import logging
            logging.info(f"{self.get_adapter_key()}: Found tables using '{strategy_used}' strategy")
        
        return self._process_tables(soup, tables, **options)
    
    def _find_tables_resilient(self, soup: BeautifulSoup) -> tuple:
        """
        Find tables using multi-strategy approach for resilience.
        
        Returns:
            Tuple of (tables_list, strategy_name)
        """
        # Strategy 1: Exact - find all <table> elements
        tables = soup.find_all("table")
        if tables:
            return tables, "exact"
        
        # Strategy 2: Fuzzy - find tables with rate-related CSS classes
        tables = self._find_tables_fuzzy_selectors(soup)
        if tables:
            return tables, "fuzzy_class"
        
        # Strategy 3: Fallback - look for div structures that might contain rates
        # (This handles table → div migrations)
        tables = self._find_div_based_tables(soup)
        if tables:
            return tables, "div_fallback"
        
        return [], "none"
    
    def _find_tables_fuzzy_selectors(self, soup: BeautifulSoup) -> list:
        """
        Find tables using fuzzy CSS class matching.
        
        Tries multiple patterns to catch CSS class renames:
        - rate.*table (matches: rate-table, rates_table, rateTable)
        - exchange.* (matches: exchange-rates, exchangeTable)
        - .*rate.* (matches: daily-rates, forex-rate-list)
        """
        import re
        
        patterns = [
            re.compile(r"rate.*table", re.I),
            re.compile(r"exchange.*", re.I),
            re.compile(r".*rate.*", re.I),
            re.compile(r"forex.*", re.I),
            re.compile(r"currency.*", re.I),
        ]
        
        for pattern in patterns:
            # Try finding tables with matching class
            tables = soup.find_all("table", class_=pattern)
            if tables:
                return tables
            
            # Try finding divs with matching class that contain tables
            divs = soup.find_all("div", class_=pattern)
            for div in divs:
                tables = div.find_all("table")
                if tables:
                    return tables
        
        return []
    
    def _find_div_based_tables(self, soup: BeautifulSoup) -> list:
        """
        Find div-based structures that replaced tables.
        
        Looks for divs with rate-related classes that might contain
        row/cell structures similar to tables.
        
        Returns empty list for now - this is a hook for future enhancement.
        """
        # TODO: Implement div-based rate container detection
        # This would detect patterns like:
        # <div class="rate-row">
        #   <div class="currency">USD</div>
        #   <div class="buying">160.50</div>
        #   <div class="selling">164.20</div>
        # </div>
        return []
    
    @abstractmethod
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """
        Extract AdapterRecords from HTML tables.
        
        Args:
            soup: BeautifulSoup parsed HTML
            tables: List of table elements found in HTML
            **options: Additional parsing options (e.g., category)
            
        Returns:
            ParseResult containing extracted records and any errors
        """
        pass
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """
        Default HTML table fingerprinting: hash table count and headers.
        
        Override for more sophisticated fingerprinting.
        
        Args:
            raw_content: Raw HTML string
            
        Returns:
            SHA256 hex digest of table structure
        """
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
    """
    Base class for text extraction adapters.
    
    Handles HTML parsing and text normalization.
    Subclasses must implement _extract_from_text() to extract records from normalized text.
    
    Example:
        class AhaduAdapter(HTMLTextAdapter):
            def _extract_from_text(self, text: str, soup: BeautifulSoup) -> ParseResult:
                result = ParseResult()
                # Extract records using regex patterns on text
                return result
            
            def get_source_url(self) -> str:
                return "https://example.com/rates"
            
            def get_adapter_key(self) -> str:
                return "example_text"
    """
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        Parse HTML content, normalize text, and delegate to _extract_from_text().
        
        Args:
            raw_content: Raw HTML string
            **options: Additional options passed to _extract_from_text()
            
        Returns:
            ParseResult from _extract_from_text()
        """
        soup = BeautifulSoup(raw_content, "html.parser")
        # Normalize whitespace: get all text and join with single spaces
        text = " ".join(soup.get_text(" ", strip=True).split())
        
        return self._extract_from_text(text, soup, **options)
    
    @abstractmethod
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        """
        Extract AdapterRecords from normalized HTML text.
        
        Args:
            text: Normalized text with single-space separation
            soup: BeautifulSoup parsed HTML (for additional extraction if needed)
            **options: Additional parsing options (e.g., category)
            
        Returns:
            ParseResult containing extracted records and any errors
        """
        pass
