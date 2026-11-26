"""
Awash Bank adapter - Clean architecture implementation.

Migration notes:
- Old adapter: 308 LOC with AJAX/Cloudflare/Playwright automation
- New adapter: ~100 LOC clean architecture (documented stub)
- Status: NEEDS UPDATE - API endpoint changed
- Golden file contains WordPress error (outdated)
- Original pattern: POST to wp-admin/admin-ajax.php with nonce extraction

AJAX endpoint: https://awashbank.com/wp-admin/admin-ajax.php

Expected response structure (when working):
{
    "success": true,
    "data": {
        "date": "2024-11-26",
        "rates": {
            "USD": {
                "buying": "120.50",
                "selling": "122.30",
                "transaction_buying": "119.80",
                "transaction_selling": "121.50",
                "weighted_buying_average": "120.00",
                "weighted_selling_average": "121.90"
            },
            ...
        }
    }
}

TODO: Update when API endpoint is confirmed working
Current implementation: Returns empty result with appropriate warning
"""

import json
from datetime import date
from decimal import Decimal
from typing import Optional

from adapters.core.contract import (
    ParseContext,
    ParseOutcome,
    RowIssue,
    IssueCode,
    Severity,
)
from adapters.core.record_builder import build_record
from adapters.core.numbers import parse_decimal
from adapters.transport.base import FetchKind


ADAPTER_KEY = "awash_ajax"
SOURCE_URL = "https://awashbank.com/wp-admin/admin-ajax.php"


class AwashAdapter:
    """
    Awash Bank AJAX adapter following new architecture.
    
    Note: This is a stub adapter. The AJAX endpoint structure has changed
    and the original patterns no longer work.
    
    The old adapter used:
    - Playwright to extract WordPress nonce from home page
    - POST request to wp-admin/admin-ajax.php with nonce
    - Cloudflare bypass techniques
    - Complex fallback strategies
    
    This adapter needs to be updated when the new API structure
    is analyzed.
    """
    
    key = ADAPTER_KEY
    url = SOURCE_URL
    fetch_kind = FetchKind.HTTP_POST  # AJAX endpoint requires POST
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse Awash Bank AJAX response.
        
        Returns empty result with warning - API structure changed.
        """
        # Check for empty input
        if not raw or not raw.strip():
            return ParseOutcome.failed(
                IssueCode.EMPTY_PAYLOAD,
                "Empty response body"
            )
        
        if "critical error" in raw.lower() and "wordpress" in raw.lower():
            return ParseOutcome.failed(
                IssueCode.NO_TABLE,
                "WordPress critical error - API endpoint not functional"
            )
        
        # Try to parse as JSON (expected format)
        try:
            data = json.loads(raw)
            
            if not data.get("success"):
                return ParseOutcome.failed(
                    IssueCode.NO_TABLE,
                    f"API returned success=false: {data.get('data', 'unknown error')}"
                )
            
            # If we get here, the structure might be valid but we need implementation
            return ParseOutcome(
                records=(),
                rows_seen=0,
                issues=(
                    RowIssue(
                        "page",
                        IssueCode.NO_TABLE,
                        "API structure changed - adapter implementation needs update. "
                        "JSON response received but parsing logic not implemented.",
                        Severity.WARNING,
                    ),
                ),
                structure_hash="awash:needs_implementation",
            )
            
        except json.JSONDecodeError:
            # Not JSON - probably HTML error page
            return ParseOutcome.failed(
                IssueCode.BAD_JSON,
                "Response is not JSON - likely error page or Cloudflare challenge"
            )


ADAPTER = AwashAdapter()
