"""
Unified parsing module for clean architecture adapters.

Handles:
- ParseContext creation from source metadata
- ParseOutcome handling (clean architecture)
- Structured error handling

Usage:
    from scheduler.parsing import parse_with_adapter
    
    outcome = parse_with_adapter(adapter, raw_content, source)
    records = outcome.records
    issues = outcome.issues
"""

import logging
from datetime import date
from typing import Any, Tuple, List

from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, Severity
from adapters.core.protocol import UniversalAdapter, is_universal_adapter
from domain.records import AdapterRecord

logger = logging.getLogger(__name__)


def create_parse_context(
    source: dict,
    collection_date: date = None,
) -> ParseContext:
    """
    Create ParseContext from source metadata.
    
    Args:
        source: Source record from database
        collection_date: Collection date (defaults to today)
    
    Returns:
        ParseContext for adapter parsing
    
    Example:
        >>> source = {"source_id": 1, "default_category": "cash"}
        >>> ctx = create_parse_context(source)
    """
    return ParseContext(
        category=source.get("default_category") or "cash",
        collection_date=collection_date or date.today(),
        source_id=source.get("source_id") or source.get("id", 0),
    )


def parse_with_adapter(
    adapter: Any,
    raw_content: str,
    source: dict,
    collection_date: date = None,
    adapter_config: dict = None,
) -> ParseOutcome:
    """
    Parse raw content using clean architecture adapter.
    
    All adapters now implement UniversalAdapter protocol and return ParseOutcome.
    
    Args:
        adapter: Adapter instance (UniversalAdapter)
        raw_content: Raw content to parse
        source: Source metadata dict
        collection_date: Optional collection date
        adapter_config: Optional adapter-specific config
    
    Returns:
        ParseOutcome with records and issues
    
    Example:
        >>> adapter = registry.get("cbe_api")
        >>> outcome = parse_with_adapter(adapter, raw_json, source)
        >>> print(f"Parsed {len(outcome.records)} records")
    """
    adapter_key = source.get("adapter_key", "unknown")
    
    # All adapters implement UniversalAdapter protocol
    if not is_universal_adapter(adapter):
        logger.error(f"Adapter {adapter_key} does not implement UniversalAdapter protocol")
        return ParseOutcome(
            records=tuple(),
            issues=(RowIssue(
                row_ref="page",
                code="bad_json",
                detail=f"Adapter does not implement UniversalAdapter protocol",
                severity=Severity.ERROR,
            ),),
            rows_seen=0,
            structure_hash=None,
        )
    
    ctx = create_parse_context(source, collection_date)
    
    try:
        outcome = adapter.parse(raw_content, ctx)
        
        if not isinstance(outcome, ParseOutcome):
            logger.warning(
                f"Adapter {adapter_key} returned {type(outcome).__name__}, "
                f"expected ParseOutcome"
            )
            return _convert_to_parse_outcome(outcome, adapter_key)
        
        logger.info(
            f"Adapter {adapter_key} parsed: {len(outcome.records)} records, "
            f"{len(outcome.issues)} issues"
        )
        return outcome
        
    except Exception as e:
        # Protocol says parse shouldn't raise, but handle it gracefully
        logger.error(
            f"Adapter {adapter_key} raised exception (protocol violation): {e}",
            exc_info=True
        )
        return ParseOutcome(
            records=tuple(),
            issues=(RowIssue(
                row_ref="page",
                code="bad_json",
                detail=f"Adapter raised exception: {str(e)}",
                severity=Severity.ERROR,
            ),),
            rows_seen=0,
            structure_hash=None,
        )


def _convert_to_parse_outcome(result: Any, adapter_key: str) -> ParseOutcome:
  
    logger.error(f"Cannot convert {type(result).__name__} to ParseOutcome")
    
    return ParseOutcome(
        records=tuple(),
        issues=(RowIssue(
            row_ref="page",
            code="bad_json",
            detail=f"Adapter returned unexpected type: {type(result).__name__}",
            severity=Severity.ERROR,
        ),),
        rows_seen=0,
        structure_hash=None,
    )


def extract_errors_and_warnings(outcome: ParseOutcome) -> Tuple[List[str], List[str]]:
    """
    Extract error and warning strings from ParseOutcome.
    
    Args:
        outcome: ParseOutcome with issues
    
    Returns:
        Tuple of (errors, warnings) as string lists
    
    Example:
        >>> outcome = parse_with_adapter(adapter, raw, source)
        >>> errors, warnings = extract_errors_and_warnings(outcome)
    """
    errors = []
    warnings = []
    
    for issue in outcome.issues:
        message = f"[{issue.row_ref}] {issue.detail}"
        
        if issue.severity == Severity.ERROR:
            errors.append(message)
        else:
            warnings.append(message)
    
    return errors, warnings
