"""
adapters/enat/adapter.py — Enat Bank (Type G text, date in text).

Parse rules:
- No table. Rates in page text: "Currency Buying Selling USD NNN NNN EUR NNN NNN ..."
- Date in text: "Oct 12, 2026" → source_published.
- Only one visible category in static HTML (Cash tab active) → category UNKNOWN until verified.
- Partial failure: returns (records, errors). Never raises.

MIGRATION NOTE: Migrated to FieldStructureMixin for automatic category detection.
"""
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTextAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "enat_html"
SOURCE_URL = "https://www.enatbanksc.com/"

_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_DATE_RE = re.compile(rf"({_MONTHS})\w*\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Matches: "USD 161.3750 164.6025" after "Currency Buying Selling" header
_RATE_RE = re.compile(r"([A-Z]{3})\s+([\d.]+)\s+([\d.]+)")

# Anchor: find the rate block after "Currency Buying Selling"
_BLOCK_START = re.compile(r"Currency\s+Buying\s+Selling", re.IGNORECASE)


class EnatAdapter(FieldStructureMixin, HTMLTextAdapter):
    """
    Enat Bank adapter with field detection.
    
    Type G adapter that extracts rates from text patterns.
    Field Structure: Generic fields → category from context (default transactional)
    """
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return Enat Bank source URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return adapter key identifier."""
        return ADAPTER_KEY
    
    def requires_category(self) -> bool:
        """Type G adapter requires category parameter."""
        return True
    
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        """
        Extract AdapterRecords from normalized HTML text using regex patterns and field detection.
        
        Args:
            text: Normalized text with single-space separation
            soup: BeautifulSoup parsed HTML (unused for Enat)
            **options: Must contain 'category' parameter
            
        Returns:
            ParseResult containing extracted records and any errors
        """
        result = ParseResult()
        
        # Extract category from options (default to cash based on visible tab)
        category = options.get("category", "cash")
        
        # Extract effective date from text
        effective_date = _extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        # Find the rate block
        m_start = _BLOCK_START.search(text)
        if not m_start:
            return result
        
        rate_text = text[m_start.end():]
        seen = set()
        
        # Extract rates using regex pattern
        for m in _RATE_RE.finditer(rate_text):
            code = m.group(1).upper()
            if code in seen:
                break  # stop at repeated codes (currency converter section)
            seen.add(code)
            try:
                # Create dict with generic field names
                row_dict = {
                    "buying": m.group(2),
                    "selling": m.group(3),
                }
                
                # Use field detection
                detected_records = self.detect_and_emit(
                    data=row_dict,
                    currency=code,
                    effective_date=effective_date,
                    effective_date_basis=date_basis,
                    mapping_notes=["category_unknown:only_cash_tab_visible_in_static_html"]
                )
                
                # Context-based category override
                for rec in detected_records:
                    if rec.category == 'UNKNOWN':
                        rec.category = normalize_category(category)
                
                result.records.extend(detected_records)
                
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
            import hashlib
            soup = BeautifulSoup(raw_content, "html.parser")
            text = " ".join(soup.get_text(" ", strip=True).split())
            markers = ["Currency Buying Selling", "Swift"]
            present = [m for m in markers if m in text]
            return hashlib.sha256(str(present).encode()).hexdigest()
        except Exception:
            import hashlib
            return hashlib.sha256(b"enat:unparseable").hexdigest()


def _extract_date(text: str) -> Optional[date]:
    """Extract date from text using month name pattern."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    month = _MONTH_MAP.get(m.group(1).lower()[:3])
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(2)))
    except ValueError:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Backward Compatibility Wrappers
# ═══════════════════════════════════════════════════════════════════════════════

def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    """
    Old function API (for backward compatibility).
    
    New code should use EnatAdapter().parse().
    
    Args:
        raw_html: Raw HTML string from Enat Bank
        category: Rate category (defaults to "UNKNOWN")
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = EnatAdapter()
    result = adapter.parse(raw_html, category=category)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use EnatAdapter().schema_fingerprint().
    
    Args:
        raw_html: Raw HTML string
        
    Returns:
        SHA256 hex digest of structural signature
    """
    return EnatAdapter().schema_fingerprint(raw_html)
