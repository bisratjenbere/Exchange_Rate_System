"""
CategoryMapper: Maps field names to canonical categories.

This module provides field-to-category mapping with support for explicit
configurations, default fallbacks, and context-aware normalization using
the existing category_normalizer module.
"""

from typing import Dict, Optional
from pipeline.category_normalizer import normalize_category_with_context
from .detector import FieldPair


class CategoryMapper:
    """Maps field names to canonical categories."""
    
    def __init__(self, 
                 default_category: str = "UNKNOWN",
                 field_mappings: Optional[Dict[str, str]] = None,
                 adapter_context: Optional[str] = None):
        """
        Initialize mapper with optional configuration.
        
        Args:
            default_category: Fallback category when field is ambiguous
            field_mappings: Explicit field-to-category mappings
            adapter_context: Adapter name for context-aware normalization
        """
        self.default_category = default_category
        self.field_mappings = field_mappings or {}
        self.adapter_context = adapter_context
    
    def map_field_to_category(self, field_name: str) -> str:
        """
        Map a field name to canonical category.
        
        Args:
            field_name: API field name (e.g., "cashBuying", "tra_buying")
        
        Returns:
            Canonical category: "cash", "transactional", "weighted_average", 
                               "indicative_reference", or default
        
        Example:
            mapper = CategoryMapper(default_category="transactional")
            mapper.map_field_to_category("cashBuying")  # → "cash"
            mapper.map_field_to_category("tra_buying")  # → "transactional"
            mapper.map_field_to_category("buying")      # → "transactional" (default)
        """
        # Check explicit mappings first (highest priority)
        if field_name in self.field_mappings:
            return self.field_mappings[field_name]
        
        # Use category normalizer with field name as context
        context = {"field_name": field_name}
        if self.adapter_context:
            context["adapter"] = self.adapter_context
        
        category = normalize_category_with_context("", context)
        
        # If normalizer returns UNKNOWN, use adapter default
        if category == "UNKNOWN":
            return self.default_category
        
        return category
    
    def map_field_pair(self, field_pair: FieldPair) -> str:
        """
        Map a field pair to category (uses buying field as representative).
        
        Args:
            field_pair: FieldPair with buy_field and sell_field
        
        Returns:
            Canonical category for the pair
        """
        return self.map_field_to_category(field_pair.buy_field)
