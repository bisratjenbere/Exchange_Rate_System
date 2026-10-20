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
        Parse HTML content, extract tables, and delegate to _process_tables().
        
        Args:
            raw_content: Raw HTML string
            **options: Additional options passed to _process_tables()
            
        Returns:
            ParseResult from _process_tables() or error if no tables found
        """
        soup = BeautifulSoup(raw_content, "html.parser")
        tables = soup.find_all("table")
        
        if not tables:
            result = ParseResult()
            result.add_error("No tables found in HTML")
            return result
        
        return self._process_tables(soup, tables, **options)
    
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
