import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class FieldPair:
    buy_field: str
    sell_field: str
    confidence: float = 1.0

    def __str__(self):
        return f"({self.buy_field}, {self.sell_field})"

class FieldDetector:

    def __init__(self, field_patterns: Optional[list] = None):
        self.field_patterns = field_patterns or []
        self._default_patterns = self._build_default_patterns()

    def detect_field_pairs(self, data: dict) -> List[FieldPair]:
        if not data:
            return []

        fields = set(data.keys())
        detected_pairs = []
        used_fields = set()

        patterns = []
        if isinstance(self.field_patterns, list):
            patterns.extend(self.field_patterns)
        patterns.extend(self._default_patterns)

        for buy_pattern, sell_pattern in patterns:
            matched_pair = self._match_pair(fields - used_fields, buy_pattern, sell_pattern)
            if matched_pair:
                buy_field, sell_field = matched_pair
                confidence = self._calculate_confidence(buy_pattern)
                detected_pairs.append(FieldPair(buy_field, sell_field, confidence))
                used_fields.add(buy_field)
                used_fields.add(sell_field)

        return detected_pairs

    def _build_default_patterns(self) -> List[Tuple[str, str]]:
        return [
            (r"^cashBuying(_?\d+)?$", r"^cashSelling(_?\d+)?$"),
            (r"^transactionalBuying(_?\d+)?$", r"^transactionalSelling(_?\d+)?$"),
            (r"^weightedBuying(_?\d+)?$", r"^weightedSelling(_?\d+)?$"),

            (r"^cash[_\-\s]?buying[_\-\s]?rate(_?\d+)?$", r"^cash[_\-\s]?selling[_\-\s]?rate(_?\d+)?$"),
            (r"^weighted[_\-\s]?buying[_\-\s]?rate(_?\d+)?$", r"^weighted[_\-\s]?selling[_\-\s]?rate(_?\d+)?$"),
            (r"^tra[_\-\s]?buying[_\-\s]?rate(_?\d+)?$", r"^tra[_\-\s]?selling[_\-\s]?rate(_?\d+)?$"),
            (r"^trans.*buying[_\-\s]?rate(_?\d+)?$", r"^trans.*selling[_\-\s]?rate(_?\d+)?$"),

            (r"^cash[_\-\s]?buying(_?\d+)?$", r"^cash[_\-\s]?selling(_?\d+)?$"),
            (r"^weighted.*buying.*$", r"^weighted.*selling.*$"),
            (r"^tra[_\-\s]?buying(_?\d+)?$", r"^tra[_\-\s]?selling(_?\d+)?$"),
            (r"^trans.*buying(_?\d+)?$", r"^trans.*selling(_?\d+)?$"),

            (r"^buyingRate(_?\d+)?$", r"^sellingRate(_?\d+)?$"),
            (r"^buyRate(_?\d+)?$", r"^sellRate(_?\d+)?$"),

            (r"^buy[_\-\s]?r(ate)?(_?\d+)?$", r"^sell[_\-\s]?r(ate)?(_?\d+)?$"),
            (r"^buy[_\-\s]?rt(_?\d+)?$", r"^sell[_\-\s]?rt(_?\d+)?$"),

            (r"^buying(_?\d+)?$", r"^selling(_?\d+)?$"),
            (r"^buying[_\-\s]?rate(_?\d+)?$", r"^selling[_\-\s]?rate(_?\d+)?$"),
            (r"^buy[_\-\s]?rate(_?\d+)?$", r"^sell[_\-\s]?rate(_?\d+)?$"),
            (r"^buy(_?\d+)?$", r"^sell(_?\d+)?$"),
        ]

    def _match_pair(self, fields: set, buy_pattern: str, sell_pattern: str) -> Optional[Tuple[str, str]]:
        buy_field = None
        sell_field = None

        for field in fields:
            if re.match(buy_pattern, field, re.IGNORECASE):
                buy_field = field
            if re.match(sell_pattern, field, re.IGNORECASE):
                sell_field = field

        if buy_field and sell_field:
            return (buy_field, sell_field)
        return None

    def _calculate_confidence(self, buy_pattern: str) -> float:
        if "cash" in buy_pattern.lower() or "trans" in buy_pattern.lower() or "weighted" in buy_pattern.lower():
            return 1.0
        return 0.8
