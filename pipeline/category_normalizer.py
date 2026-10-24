"""
pipeline/category_normalizer.py — normalize scraped category strings to canonical values.

Problem: Adapters scrape category labels from bank websites which use inconsistent naming:
- "CASH", "Cash", "cash", "cash buying"
- "TRANSACTION", "Transaction", "transactional", "non-cash"
- "WEIGHTED AVERAGE", "Weighted", "Average", "weighted_average"

This module provides pattern-based normalization to map all variations to canonical category codes.

LOCKED rules:
- Only four canonical categories: cash, transactional, weighted_average, indicative_reference
- Unknown/ambiguous → UNKNOWN (excluded from trusted view)
- Case-insensitive matching
- Partial matches acceptable (e.g., "trans" → "transactional")
- Returns UNKNOWN if no pattern matches
"""
import re
from typing import Optional


# Canonical category codes (must match rate_category.code in database)
CANONICAL_CATEGORIES = {
    "cash",
    "transactional",
    "weighted_average",
    "indicative_reference",
}

# Pattern-based normalization rules
# Order matters: more specific patterns first
NORMALIZATION_PATTERNS = [
    # ============================================================================
    # TRANSACTIONAL patterns (BEFORE cash - non-cash must match before cash)
    # ============================================================================
    (r'^non[_\s\-]?cash$', 'transactional'),  # non-cash, non_cash → transactional
    (r'^transactional$', 'transactional'),
    (r'^transaction$', 'transactional'),
    (r'^trans$', 'transactional'),
    (r'^txn$', 'transactional'),
    (r'transact', 'transactional'),          # transactional, transaction, transact
    (r'\btrans\b', 'transactional'),         # "Trans Buying"
    (r'\btxn\b', 'transactional'),           # "TXN Rate"
    
    # ============================================================================
    # CASH patterns (AFTER non-cash patterns)
    # ============================================================================
    (r'^cash$', 'cash'),
    (r'^cash[_\s-]', 'cash'),  # cash_buying, cash buying, cash-buying
    (r'\bcash\b', 'cash'),     # "Foreign Exchange Cash Rate"
    
    # ============================================================================
    # WEIGHTED_AVERAGE patterns  
    # ============================================================================
    (r'^weighted[_\s-]?average$', 'weighted_average'),
    (r'^weighted$', 'weighted_average'),
    (r'^average$', 'weighted_average'),      # Context: if alone likely weighted
    (r'^avg$', 'weighted_average'),
    (r'weighted.*average', 'weighted_average'),
    (r'average.*weighted', 'weighted_average'),
    (r'\bweighted\b', 'weighted_average'),   # "Weighted Rate"
    
    # ============================================================================
    # INDICATIVE_REFERENCE patterns (rare)
    # ============================================================================
    (r'^indicative', 'indicative_reference'),
    (r'^reference', 'indicative_reference'),
    (r'indicative.*reference', 'indicative_reference'),
    (r'reference.*rate', 'indicative_reference'),
]


def normalize_category(raw_category: str) -> str:
    """
    Normalize a scraped category string to canonical category code.
    
    Args:
        raw_category: Raw category string from bank website
                     (e.g., "CASH", "Transaction", "non-cash", "Weighted Average")
    
    Returns:
        Canonical category code: 'cash', 'transactional', 'weighted_average', 
                                'indicative_reference', or 'UNKNOWN'
    
    Examples:
        >>> normalize_category("CASH")
        'cash'
        >>> normalize_category("Transaction")
        'transactional'
        >>> normalize_category("non-cash")
        'transactional'
        >>> normalize_category("Weighted Average Rate")
        'weighted_average'
        >>> normalize_category("forex")
        'UNKNOWN'
    """
    if not raw_category or not isinstance(raw_category, str):
        return "UNKNOWN"
    
    # Already canonical
    cleaned = raw_category.strip().lower()
    if cleaned in CANONICAL_CATEGORIES:
        return cleaned
    
    # Remove common noise words and characters
    cleaned = re.sub(r'[():]', ' ', cleaned)  # Remove parens and colons
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()  # Normalize whitespace
    
    # Try pattern matching
    for pattern, canonical in NORMALIZATION_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            return canonical
    
    # No match found
    return "UNKNOWN"


def normalize_category_with_context(raw_category: str, context: dict = None) -> str:
    """
    Normalize category with additional context clues.
    
    Args:
        raw_category: Raw category string
        context: Optional dict with hints:
                 - 'field_name': API field name (e.g., 'cashBuying', 'tra_buying')
                 - 'column_header': Table column header text
                 - 'table_index': Which table in multi-table layout
    
    Returns:
        Canonical category code or 'UNKNOWN'
    
    Examples:
        >>> normalize_category_with_context("", {"field_name": "cashBuying"})
        'cash'
        >>> normalize_category_with_context("", {"field_name": "tra_buying"})
        'transactional'
    """
    if not context:
        return normalize_category(raw_category)
    
    # Try direct category first
    result = normalize_category(raw_category)
    if result != "UNKNOWN":
        return result
    
    # Check field_name context
    if 'field_name' in context:
        field = context['field_name'].lower()
        
        # API field patterns
        if 'cash' in field:
            return 'cash'
        if any(x in field for x in ['trans', 'txn', 'tra_']):
            return 'transactional'
        if 'weighted' in field or 'average' in field:
            return 'weighted_average'
    
    # Check column_header context
    if 'column_header' in context:
        header = context['column_header'].lower()
        return normalize_category(header)
    
    return "UNKNOWN"


def validate_category(category: str) -> bool:
    """
    Check if a category string is a valid canonical category.
    
    Args:
        category: Category string to validate
    
    Returns:
        True if valid canonical category, False otherwise
    """
    return category in CANONICAL_CATEGORIES


def get_canonical_categories() -> set:
    """Return set of all valid canonical category codes."""
    return CANONICAL_CATEGORIES.copy()


# ============================================================================
# Testing / Validation
# ============================================================================

if __name__ == "__main__":
    # Test cases from real adapters
    test_cases = [
        # (input, expected_output)
        ("CASH", "cash"),
        ("Cash", "cash"),
        ("cash", "cash"),
        ("cash buying", "cash"),
        ("cash_buying", "cash"),
        
        ("TRANSACTION", "transactional"),
        ("Transaction", "transactional"),
        ("transactional", "transactional"),
        ("trans", "transactional"),
        ("txn", "transactional"),
        ("non-cash", "transactional"),
        ("non_cash", "transactional"),
        
        ("WEIGHTED AVERAGE", "weighted_average"),
        ("Weighted Average", "weighted_average"),
        ("weighted_average", "weighted_average"),
        ("Weighted", "weighted_average"),
        ("Average", "weighted_average"),
        ("avg", "weighted_average"),
        
        ("indicative", "indicative_reference"),
        ("reference rate", "indicative_reference"),
        
        ("forex", "UNKNOWN"),
        ("", "UNKNOWN"),
        (None, "UNKNOWN"),
        ("something_random", "UNKNOWN"),
    ]
    
    print("Category Normalization Test Cases")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for input_val, expected in test_cases:
        result = normalize_category(input_val)
        status = "✓" if result == expected else "✗"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
            
        print(f"{status} {repr(input_val):<25} → {result:<20} (expected: {expected})")
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    
    # Test context-based normalization
    print("\nContext-Based Normalization Tests")
    print("=" * 60)
    
    context_tests = [
        ("", {"field_name": "cashBuying"}, "cash"),
        ("", {"field_name": "tra_buying"}, "transactional"),
        ("", {"field_name": "transactionSelling"}, "transactional"),
        ("", {"field_name": "weightedBuying"}, "weighted_average"),
    ]
    
    for input_val, context, expected in context_tests:
        result = normalize_category_with_context(input_val, context)
        status = "✓" if result == expected else "✗"
        print(f"{status} field={context.get('field_name'):<20} → {result:<20} (expected: {expected})")
