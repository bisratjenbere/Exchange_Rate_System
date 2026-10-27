import re
from typing import Optional

CANONICAL_CATEGORIES = {
    "cash",
    "transactional",
    "weighted_average",
    "indicative_reference",
}

NORMALIZATION_PATTERNS = [
    (r'^non[_\s\-]?cash$', 'transactional'),
    (r'^transactional$', 'transactional'),
    (r'^transaction$', 'transactional'),
    (r'^trans$', 'transactional'),
    (r'^txn$', 'transactional'),
    (r'transact', 'transactional'),
    (r'\btrans\b', 'transactional'),
    (r'\btxn\b', 'transactional'),

    (r'^cash$', 'cash'),
    (r'^cash[_\s-]', 'cash'),
    (r'\bcash\b', 'cash'),

    (r'^weighted[_\s-]?average$', 'weighted_average'),
    (r'^weighted$', 'weighted_average'),
    (r'^average$', 'weighted_average'),
    (r'^avg$', 'weighted_average'),
    (r'weighted.*average', 'weighted_average'),
    (r'average.*weighted', 'weighted_average'),
    (r'\bweighted\b', 'weighted_average'),

    (r'^indicative', 'indicative_reference'),
    (r'^reference', 'indicative_reference'),
    (r'indicative.*reference', 'indicative_reference'),
    (r'reference.*rate', 'indicative_reference'),
]

def normalize_category(raw_category: str) -> str:
    if not raw_category or not isinstance(raw_category, str):
        return "UNKNOWN"

    cleaned = raw_category.strip().lower()
    if cleaned in CANONICAL_CATEGORIES:
        return cleaned

    cleaned = re.sub(r'[():]', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    for pattern, canonical in NORMALIZATION_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            return canonical

    return "UNKNOWN"

def normalize_category_with_context(raw_category: str, context: dict = None) -> str:
    if not context:
        return normalize_category(raw_category)

    result = normalize_category(raw_category)
    if result != "UNKNOWN":
        return result

    if 'field_name' in context:
        field = context['field_name'].lower()

        if 'cash' in field:
            return 'cash'
        if any(x in field for x in ['trans', 'txn', 'tra_']):
            return 'transactional'
        if 'weighted' in field or 'average' in field:
            return 'weighted_average'

    if 'column_header' in context:
        header = context['column_header'].lower()
        return normalize_category(header)

    return "UNKNOWN"

def validate_category(category: str) -> bool:
    return category in CANONICAL_CATEGORIES

def get_canonical_categories() -> set:
    return CANONICAL_CATEGORIES.copy()

if __name__ == "__main__":
    test_cases = [
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
