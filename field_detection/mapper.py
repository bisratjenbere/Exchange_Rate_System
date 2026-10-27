from typing import Dict, Optional
from pipeline.category_normalizer import normalize_category_with_context
from .detector import FieldPair

class CategoryMapper:

    def __init__(self,
                 default_category: str = "UNKNOWN",
                 field_mappings: Optional[Dict[str, str]] = None,
                 adapter_context: Optional[str] = None):
        self.default_category = default_category
        self.field_mappings = field_mappings or {}
        self.adapter_context = adapter_context

    def map_field_to_category(self, field_name: str) -> str:
        if field_name in self.field_mappings:
            return self.field_mappings[field_name]

        context = {"field_name": field_name}
        if self.adapter_context:
            context["adapter"] = self.adapter_context

        category = normalize_category_with_context("", context)

        if category == "UNKNOWN":
            return self.default_category

        return category

    def map_field_pair(self, field_pair: FieldPair) -> str:
        return self.map_field_to_category(field_pair.buy_field)
