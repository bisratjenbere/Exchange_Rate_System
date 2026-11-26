"""
Universal Adapter Protocol

Defines the interface that ALL clean architecture adapters must implement.

Design:
- Protocol (duck typing) rather than ABC for flexibility
- ParseContext provides runtime metadata (date, source, category)
- ParseOutcome returns structured errors (never raises)
- All 32 adapters satisfy this protocol (100% clean)

Usage:
    adapter: UniversalAdapter = registry.get("cbe_api")
    outcome = adapter.parse(raw_content, ctx)
    
    for record in outcome.records:
        process(record)
    
    for issue in outcome.issues:
        log_issue(issue)
"""

from typing import Protocol, Optional
from adapters.core.contract import ParseContext, ParseOutcome


class UniversalAdapter(Protocol):
    """
    Protocol that all clean architecture adapters must satisfy.
    
    This is a Protocol (PEP 544), not an ABC, so adapters don't need to
    explicitly inherit from it - they just need to have matching attributes
    and methods.
    
    Attributes:
        key: Unique adapter identifier (e.g., 'cbe_api', 'zemen_ajax')
        url: Source URL for fetching data
        fetch_kind: Optional fetch method ('http_get', 'http_post', 'browser')
    
    Methods:
        parse(raw, ctx) -> ParseOutcome: Parse raw content into structured outcome
    """
    
    key: str
    """Unique adapter identifier (e.g., 'cbe_api')"""
    
    url: str
    """Source URL for fetching data"""
    
    # Optional attributes for transport layer
    fetch_kind: Optional[str]
    """Fetch method: 'http_get', 'http_post', 'browser', etc."""
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse raw content into structured outcome.
        
        Args:
            raw: Raw content (HTML, JSON, XML, etc.)
            ctx: Parse context with metadata (date, source_id, category)
        
        Returns:
            ParseOutcome containing:
                - records: Tuple of AdapterRecord objects
                - issues: Tuple of RowIssue objects (errors and warnings)
                - rows_seen: Number of rows processed
                - structure_hash: Optional content hash for schema change detection
        
        Note:
            This method NEVER raises exceptions for parse errors.
            All errors are returned in ParseOutcome.issues.
            Only raises for programmer errors (wrong arguments, etc.)
        """
        ...


def is_universal_adapter(obj: object) -> bool:
    """
    Check if an object satisfies the UniversalAdapter protocol.
    
    Args:
        obj: Object to check
    
    Returns:
        True if object has required attributes and methods
    
    Example:
        >>> from adapters.banks.cbe_new import ADAPTER
        >>> is_universal_adapter(ADAPTER)
        True
    """
    return (
        hasattr(obj, 'key') and isinstance(obj.key, str) and
        hasattr(obj, 'url') and isinstance(obj.url, str) and
        hasattr(obj, 'parse') and callable(obj.parse)
    )


def validate_adapter(adapter: object) -> list[str]:
    """
    Validate that an adapter satisfies the UniversalAdapter protocol.
    
    Args:
        adapter: Adapter object to validate
    
    Returns:
        List of validation errors (empty if valid)
    
    Example:
        >>> errors = validate_adapter(my_adapter)
        >>> if errors:
        ...     print(f"Invalid adapter: {errors}")
    """
    errors = []
    
    if not hasattr(adapter, 'key'):
        errors.append("Missing attribute: 'key'")
    elif not isinstance(adapter.key, str):
        errors.append(f"Attribute 'key' must be str, got {type(adapter.key)}")
    
    if not hasattr(adapter, 'url'):
        errors.append("Missing attribute: 'url'")
    elif not isinstance(adapter.url, str):
        errors.append(f"Attribute 'url' must be str, got {type(adapter.url)}")
    
    if not hasattr(adapter, 'parse'):
        errors.append("Missing method: 'parse'")
    elif not callable(adapter.parse):
        errors.append("Attribute 'parse' must be callable")
    else:
        # Check parse method signature
        import inspect
        sig = inspect.signature(adapter.parse)
        params = list(sig.parameters.keys())
        
        # Expect: parse(self, raw, ctx) or parse(raw, ctx)
        if len(params) < 2:
            errors.append(f"Method 'parse' must accept at least 2 args, got {len(params)}")
        
        # Check parameter names (allow some flexibility)
        raw_param = params[-2] if len(params) >= 2 else None
        ctx_param = params[-1] if len(params) >= 1 else None
        
        if raw_param not in ('raw', 'raw_content', 'payload', 'content'):
            errors.append(f"Second-to-last parameter should be 'raw', got '{raw_param}'")
        
        if ctx_param not in ('ctx', 'context', 'parse_context'):
            errors.append(f"Last parameter should be 'ctx', got '{ctx_param}'")
    
    return errors
