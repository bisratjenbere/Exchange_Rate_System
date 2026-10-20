"""
adapters/ahadu/adapter.py — Ahadu Bank (Type G text extraction).

Parse rules:
- No table. Rates in page text pattern:
  "CURR : CODE Buying Rate : NNN|No Trade Selling Rate : NNN|No Trade"
- Date in text: "EXCHANGE RATE FOR : DD/MM/YYYY" → source_published.
- Single buying/selling pair — category UNKNOWN (unconfirmed).
- "No Trade" → None.
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTextAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

# Module-level constants for backward compatibility
ADAPTER_KEY = "ahadu_html"
SOURCE_URL = "https://ahadubank.com/"

# Regex patterns for text extraction
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_RATE_RE = re.compile(
    r"CURR\s*:\s*([A-Z]{3})\s+Buying Rate\s*:\s*([\d.]+|No Trade)\s+Selling Rate\s*:\s*([\d.]+|No Trade)",
    re.IGNORECASE,
)


class AhaduAdapter(HTMLTextAdapter):
    """
    Ahadu Bank adapter using HTMLTextAdapter base class.
    
    Type G adapter that extracts rates from text patterns.
    Requires category parameter (Type G characteristic).
    """
    
    def get_source_url(self) -> str:
        """Return Ahadu Bank source URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return adapter key identifier."""
        return ADAPTER_KEY
    
    def requires_category(self) -> bool:
        """Type G adapter requires category parameter."""
        return True
    
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        """
        Extract AdapterRecords from normalized HTML text using regex patterns.
        
        Args:
            text: Normalized text with single-space separation
            soup: BeautifulSoup parsed HTML (unused for Ahadu)
            **options: Must contain 'category' parameter
            
        Returns:
            ParseResult containing extracted records and any errors
        """
        result = ParseResult()
        
        # Extract category from options
        category = options.get("category", "UNKNOWN")
        
        # Extract effective date from text
        effective_date = _extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        # Extract rates using regex pattern
        for m in _RATE_RE.finditer(text):
            code = m.group(1).upper()
            try:
                buying = _safe_rate(m.group(2))
                selling = _safe_rate(m.group(3))
                
                # Skip currencies with no tradeable rates
                if buying is None and selling is None:
                    continue
                
                result.records.append(AdapterRecord(
                    source_currency_code=code,
                    category=category,
                    buying_rate=buying,
                    selling_rate=selling,
                    source_rate_text=f"{m.group(2)}/{m.group(3)}",
                    effective_date=effective_date,
                    effective_date_basis=date_basis,
                    source_record_key=None,
                    source_publication_key=None,
                    unit_multiplier=1,
                    raw_excerpt={"currency": code, "buying": m.group(2), "selling": m.group(3)},
                    mapping_notes=["category_unknown:single_pair_unconfirmed"],
                ))
            except Exception as exc:
                result.add_error(f"currency:{code}:{exc}")
        
        return result
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """
        Generate schema fingerprint based on text markers.
        
        Args:
            raw_content: Raw HTML string
            
        Returns:
            SHA256 hex digest of structural markers
        """
        try:
            soup = BeautifulSoup(raw_content, "html.parser")
            text = " ".join(soup.get_text(" ", strip=True).split())
            markers = ["CURR", "Buying Rate", "Selling Rate"]
            present = [m for m in markers if m in text]
            return hashlib.sha256(str(present).encode()).hexdigest()
        except Exception:
            return hashlib.sha256(b"ahadu:unparseable").hexdigest()


# Helper functions (kept at module level for internal use)

def _extract_date(text: str) -> Optional[date]:
    """
    Extract date from text using DD/MM/YYYY pattern.
    
    Args:
        text: Normalized text to search
        
    Returns:
        date object or None if no valid date found
    """
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(year, month, day)
    except ValueError:
        return None


def _safe_rate(raw: str) -> Optional[Decimal]:
    """
    Safely convert raw rate string to Decimal.
    
    Args:
        raw: Raw rate value (may be number or "No Trade")
        
    Returns:
        Normalized Decimal rate or None if "No Trade" or invalid
    """
    if not raw or raw.strip().lower() == "no trade":
        return None
    try:
        return normalize_rate(raw.strip())
    except ValueError:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Backward Compatibility Layer
# ═══════════════════════════════════════════════════════════════════════════════

# Module-level adapter instance
_adapter = AhaduAdapter()


def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    """
    Backward compatibility wrapper for function-based parse interface.
    
    Args:
        raw_html: Raw HTML string from Ahadu Bank
        category: Rate category (defaults to "UNKNOWN")
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    result = _adapter.parse(raw_html, category=category)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Backward compatibility wrapper for function-based fingerprint interface.
    
    Args:
        raw_html: Raw HTML string
        
    Returns:
        SHA256 hex digest of structural signature
    """
    return _adapter.schema_fingerprint(raw_html)
