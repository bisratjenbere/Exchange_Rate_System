"""
adapters/ahadu/adapter.py — Ahadu Bank (Type G text extraction).

Parse rules:
- No table. Rates in page text pattern:
  "CURR : CODE Buying Rate : NNN|No Trade Selling Rate : NNN|No Trade"
- Date in text: "EXCHANGE RATE FOR : DD/MM/YYYY" → source_published.
- Single buying/selling pair — defaults to transactional category.
- "No Trade" → None.
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

# Module-level constants for backward compatibility
ADAPTER_KEY = "ahadu_html"
SOURCE_URL = "https://ahadubank.com/"

# Regex patterns for text extraction
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_RATE_RE = re.compile(
    r"CURR\s*:\s*([A-Z]{3})\s+Buying Rate\s*:\s*([\d.]+|No Trade)\s+Selling Rate\s*:\s*([\d.]+|No Trade)",
    re.IGNORECASE,
)


class AhaduAdapter(FieldStructureMixin, HTMLTextAdapter):
    """
    Ahadu Bank adapter with field detection.
    
    Type G adapter that extracts rates from text patterns.
    Field Structure: Generic fields → transactional (context-based)
    """
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return Ahadu Bank source URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return adapter key identifier."""
        return ADAPTER_KEY
    
    def requires_category(self) -> bool:
        """No longer requires category parameter - uses default."""
        return False
    
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        """
        Extract AdapterRecords from normalized HTML text using regex patterns and field detection.
        
        Args:
            text: Normalized text with single-space separation
            soup: BeautifulSoup parsed HTML (unused for Ahadu)
            **options: Optional parameters (category no longer required)
            
        Returns:
            ParseResult containing extracted records and any errors
        """
        result = ParseResult()
        
        # Extract effective date from text
        effective_date = _extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        # Extract rates using regex pattern
        for m in _RATE_RE.finditer(text):
            code = m.group(1).upper()
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
                    mapping_notes=["single_field_pair:transactional_default"]
                )
                
                # Context-based category override: single pair = transactional
                for rec in detected_records:
                    if rec.category == 'UNKNOWN':
                        rec.category = normalize_category("transactional")
                
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
            markers = ["CURR", "Buying Rate", "Selling Rate"]
            present = [m for m in markers if m in text]
            return hashlib.sha256(str(present).encode()).hexdigest()
        except Exception:
            import hashlib
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


# ═══════════════════════════════════════════════════════════════════════════════
# Backward Compatibility Layer
# ═══════════════════════════════════════════════════════════════════════════════

# Module-level adapter instance
_adapter = AhaduAdapter()


def parse(raw_html: str, category: str = None) -> tuple:
    """
    Backward compatibility wrapper for function-based parse interface.
    
    Args:
        raw_html: Raw HTML string from Ahadu Bank
        category: Optional category (deprecated, now uses default)
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    result = _adapter.parse(raw_html)
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
