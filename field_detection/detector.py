"""
FieldDetector: Identifies buying/selling field pairs in JSON structures.

This module implements pattern-based detection of exchange rate field pairs,
supporting multiple naming conventions (explicit categories, prefixes, generic).
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class FieldPair:
    """Represents a detected buying/selling field pair."""
    buy_field: str          # Field name for buying rate (e.g., "cashBuying")
    sell_field: str         # Field name for selling rate (e.g., "cashSelling")
    confidence: float = 1.0 # Confidence score (0.0-1.0)
    
    def __str__(self):
        return f"({self.buy_field}, {self.sell_field})"


class FieldDetector:
    """Detects buying/selling field pairs in JSON structures."""
    
    def __init__(self, field_patterns: Optional[dict] = None):
        """
        Initialize detector with optional field patterns.
        
        Args:
            field_patterns: Optional dict of {field_name: category_hint}
                          for explicit field-to-category mappings
        """
        self.field_patterns = field_patterns or {}
        self._default_patterns = self._build_default_patterns()
    
    def detect_field_pairs(self, data: dict) -> List[FieldPair]:
        """
        Detect all buying/selling field pairs in data structure.
        
        Args:
            data: JSON dict from API response (attributes or rate object)
        
        Returns:
            List of FieldPair objects with (buy_field, sell_field, confidence)
        
        Example:
            data = {"buying": 162.00, "tra_buying": 162.00, 
                    "selling": 165.00, "tra_selling": 165.00}
            pairs = detector.detect_field_pairs(data)
            # Returns: [
            #   FieldPair("buying", "selling", confidence=0.9),
            #   FieldPair("tra_buying", "tra_selling", confidence=0.9)
            # ]
        """
        if not data:
            return []
        
        fields = set(data.keys())
        detected_pairs = []
        used_fields = set()
        
        # Try each pattern in order (explicit categories first, generic last)
        for buy_pattern, sell_pattern in self._default_patterns:
            matched_pair = self._match_pair(fields - used_fields, buy_pattern, sell_pattern)
            if matched_pair:
                buy_field, sell_field = matched_pair
                # Assign confidence based on pattern specificity
                confidence = self._calculate_confidence(buy_pattern)
                detected_pairs.append(FieldPair(buy_field, sell_field, confidence))
                used_fields.add(buy_field)
                used_fields.add(sell_field)
        
        return detected_pairs
    
    def _build_default_patterns(self) -> List[Tuple[str, str]]:
        """
        Build default patterns for common field structures.
        
        RESILIENCE ENHANCEMENTS:
        - Handles numbered variants (buying_1, buying_2)
        - Handles hyphenated fields (cash-buying, trans-selling)
        - Handles camelCase variations (buyingRate, BuyingRate)
        - Handles abbreviated forms (buy_r, sell_r, buy_rt)
        - Handles spacing variations (buying rate, BuyingRate)
        """
        return [
            # Pattern: camelCase explicit categories (highest specificity)
            (r"^cashBuying(_?\d+)?$", r"^cashSelling(_?\d+)?$"),
            (r"^transactionalBuying(_?\d+)?$", r"^transactionalSelling(_?\d+)?$"),
            (r"^weightedBuying(_?\d+)?$", r"^weightedSelling(_?\d+)?$"),
            
            # Pattern: explicit category prefixes with _rate suffix (with variations)
            (r"^cash[_\-\s]?buying[_\-\s]?rate(_?\d+)?$", r"^cash[_\-\s]?selling[_\-\s]?rate(_?\d+)?$"),
            (r"^weighted[_\-\s]?buying[_\-\s]?rate(_?\d+)?$", r"^weighted[_\-\s]?selling[_\-\s]?rate(_?\d+)?$"),
            (r"^tra[_\-\s]?buying[_\-\s]?rate(_?\d+)?$", r"^tra[_\-\s]?selling[_\-\s]?rate(_?\d+)?$"),
            (r"^trans.*buying[_\-\s]?rate(_?\d+)?$", r"^trans.*selling[_\-\s]?rate(_?\d+)?$"),
            
            # Pattern: explicit category prefixes (with hyphen/underscore variations)
            (r"^cash[_\-\s]?buying(_?\d+)?$", r"^cash[_\-\s]?selling(_?\d+)?$"),
            (r"^weighted[_\-\s]?buying(_?\d+)?$", r"^weighted[_\-\s]?selling(_?\d+)?$"),
            (r"^tra[_\-\s]?buying(_?\d+)?$", r"^tra[_\-\s]?selling(_?\d+)?$"),
            (r"^trans.*buying(_?\d+)?$", r"^trans.*selling(_?\d+)?$"),
            
            # Pattern: camelCase generic (no category)
            (r"^buyingRate(_?\d+)?$", r"^sellingRate(_?\d+)?$"),
            (r"^buyRate(_?\d+)?$", r"^sellRate(_?\d+)?$"),
            
            # Pattern: abbreviated forms
            (r"^buy[_\-\s]?r(ate)?(_?\d+)?$", r"^sell[_\-\s]?r(ate)?(_?\d+)?$"),
            (r"^buy[_\-\s]?rt(_?\d+)?$", r"^sell[_\-\s]?rt(_?\d+)?$"),
            
            # Pattern: generic buying/selling with variations (lowest confidence)
            (r"^buying(_?\d+)?$", r"^selling(_?\d+)?$"),
            (r"^buying[_\-\s]?rate(_?\d+)?$", r"^selling[_\-\s]?rate(_?\d+)?$"),
            (r"^buy[_\-\s]?rate(_?\d+)?$", r"^sell[_\-\s]?rate(_?\d+)?$"),
            (r"^buy(_?\d+)?$", r"^sell(_?\d+)?$"),
        ]
    
    def _match_pair(self, fields: set, buy_pattern: str, sell_pattern: str) -> Optional[Tuple[str, str]]:
        """Match a buying/selling pattern against available fields."""
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
        """Calculate confidence score based on pattern specificity."""
        # Explicit category patterns have higher confidence
        if "cash" in buy_pattern.lower() or "trans" in buy_pattern.lower() or "weighted" in buy_pattern.lower():
            return 1.0
        # Generic patterns have lower confidence
        return 0.8
