"""
Anbesa Bank adapter - Clean architecture implementation.

Migration notes:
- Old adapter: 210 LOC with Browser/Playwright automation
- New adapter: ~80 LOC clean architecture (documented stub)
- Status: NEEDS UPDATE - website structure changed
- Golden file has 0 expected records (outdated)
- Original pattern: Playwright clicks on #exchangerate, #waighted, #exchange buttons
  to open popup dialogs (#hustle-popup-id-15, #hustle-slidein-id-18, etc.)

Browser automation requirements:
- Requires Playwright/Chromium
- Complex interaction: click buttons → wait for popups → extract HTML
- Multiple popup IDs: #hustle-popup-id-15, #hustle-slidein-id-18, #hustle-popup-id-10

TODO: Update parsing logic when website structure is confirmed
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


ADAPTER_KEY = "anbesa_browser"
SOURCE_URL = "https://anbesabank.com/"


class AnbesaAdapter:
    """
    Anbesa Bank adapter following new architecture.
    
    Note: This is a stub adapter. The website structure has changed
    and the original browser automation patterns no longer work.
    
    The old adapter used Playwright to:
    1. Click #exchangerate button → extract #hustle-popup-id-15
    2. Click #waighted button → extract #hustle-slidein-id-18
    3. Click #exchange button → extract #hustle-popup-id-10
    
    This adapter needs to be updated when the new website structure
    is analyzed. May or may not require browser automation.
    """
    
    key = ADAPTER_KEY
    url = SOURCE_URL
    fetch_kind = FetchKind.BROWSER  # Signals browser may be needed
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse Anbesa Bank HTML.
        
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
                    "Original browser automation patterns (Playwright, hustle popups) not found or not functional.",
                    Severity.WARNING,
                ),
            ),
            structure_hash="anbesa:needs_update",
        )


ADAPTER = AnbesaAdapter()
