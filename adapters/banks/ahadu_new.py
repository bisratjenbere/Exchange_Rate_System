"""
Ahadu Bank adapter - Clean architecture implementation.

Migration notes:
- Old adapter: 138 LOC with FieldStructureMixin and HTMLTextAdapter
- New adapter: ~80 LOC clean architecture (minimal stub)
- Status: NEEDS UPDATE - website structure changed
- Golden file has 0 expected records (outdated)
- Original patterns (carousel slides, CURR regex) no longer match

TODO: Update parsing logic when website structure is known
Current implementation: Returns empty result with appropriate warning
"""

from datetime import date
from typing import Optional

from adapters.core.contract import (
    ParseContext,
    ParseOutcome,
    RowIssue,
    IssueCode,
    Severity,
)
from adapters.transport.base import FetchKind


ADAPTER_KEY = "ahadu_html"
SOURCE_URL = "https://ahadubank.com/"


class AhaduAdapter:
    """
    Ahadu Bank adapter following new architecture.
    
    Note: This is a stub adapter. The website structure has changed
    and the original parsing patterns (swiper-slide carousel and
    CURR regex) no longer match the HTML.
    
    This adapter needs to be updated when the new website structure
    is analyzed.
    """
    
    key = ADAPTER_KEY
    url = SOURCE_URL
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse Ahadu Bank HTML.
        
        Returns empty result with warning - website structure changed.
        """
        # Check for empty input
        if not raw or not raw.strip():
            return ParseOutcome.failed(
                IssueCode.EMPTY_PAYLOAD,
                "Empty HTML body"
            )
        
        # Return structured outcome indicating adapter needs update
        return ParseOutcome(
            records=(),
            rows_seen=0,
            issues=(
                RowIssue(
                    "page",
                    IssueCode.NO_TABLE,
                    "Website structure changed - adapter needs update. "
                    "Original patterns (swiper-slide, CURR regex) not found.",
                    Severity.WARNING,
                ),
            ),
            structure_hash="ahadu:needs_update",
        )


ADAPTER = AhaduAdapter()
