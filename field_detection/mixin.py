"""
FieldStructureMixin: Composition mixin for adapters.

Provides field-structure-based category detection functionality to adapters
through composition, without modifying base class hierarchy.
"""

from datetime import date
from typing import List, Optional

from domain.records import AdapterRecord
from .detector import FieldDetector
from .mapper import CategoryMapper
from .emitter import RecordEmitter


class FieldStructureMixin:
    """
    Mixin providing field-structure-based category detection.
    
    Adapters using this mixin should:
    1. Inherit from both JSONAdapter and FieldStructureMixin
    2. Define FIELD_CONFIG class attribute (optional)
    3. Call detect_and_emit() from _parse_item() method
    
    Example:
        class WegagenAdapter(JSONAdapter, FieldStructureMixin):
            FIELD_CONFIG = {
                "field_mappings": {
                    "buying": "cash",
                    "tra_buying": "transactional"
                },
                "default_category": "transactional"
            }
            
            def _parse_item(self, item: dict) -> list:
                attrs = item["attributes"]
                return self.detect_and_emit(
                    attrs,
                    currency=attrs["code"],
                    source_record_id=item["id"],
                    effective_date=self._parse_iso_date(attrs["date"])
                )
    """
    
    # Configuration attribute (override in subclass)
    FIELD_CONFIG: dict = {}
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._detector = None
        self._mapper = None
        self._emitter = None
    
    @property
    def field_detector(self) -> FieldDetector:
        """Lazy-initialize FieldDetector from config."""
        if self._detector is None:
            config = self.FIELD_CONFIG
            field_patterns = config.get("field_patterns")
            self._detector = FieldDetector(field_patterns=field_patterns)
        return self._detector
    
    @property
    def category_mapper(self) -> CategoryMapper:
        """Lazy-initialize CategoryMapper from config."""
        if self._mapper is None:
            config = self.FIELD_CONFIG
            self._mapper = CategoryMapper(
                default_category=config.get("default_category", "UNKNOWN"),
                field_mappings=config.get("field_mappings"),
                adapter_context=self.get_adapter_key()
            )
        return self._mapper
    
    @property
    def record_emitter(self) -> RecordEmitter:
        """Lazy-initialize RecordEmitter."""
        if self._emitter is None:
            self._emitter = RecordEmitter()
        return self._emitter
    
    def detect_and_emit(
        self,
        data: dict,
        *,
        currency: str,
        effective_date: Optional[date] = None,
        effective_date_basis: str = "collection_date_fallback",
        source_record_id: Optional[str] = None,
        source_publication_id: Optional[str] = None,
        unit_multiplier: int = 1,
        currency_name: Optional[str] = None,
        quote_currency: Optional[str] = None,
        mapping_notes: Optional[List[str]] = None
    ) -> List[AdapterRecord]:
        """
        One-line method to detect field structure and emit records.
        
        This is the primary entry point for adapters using the mixin.
        
        Args:
            data: Dict containing rate fields (e.g., item["attributes"])
            currency: Source currency code
            effective_date: Effective date from source
            effective_date_basis: Date basis indicator
            source_record_id: Source record ID
            source_publication_id: Publication ID
            unit_multiplier: Unit multiplier
            currency_name: Optional currency name
            quote_currency: Optional quote currency
            mapping_notes: Optional mapping notes
        
        Returns:
            List of AdapterRecord objects
        """
        # Step 1: Detect field pairs
        field_pairs = self.field_detector.detect_field_pairs(data)
        
        # Step 2: Emit records with category mapping
        return self.record_emitter.emit_records_from_fields(
            data,
            field_pairs,
            self.category_mapper,
            currency=currency,
            effective_date=effective_date,
            effective_date_basis=effective_date_basis,
            source_record_id=source_record_id,
            source_publication_id=source_publication_id,
            unit_multiplier=unit_multiplier,
            currency_name=currency_name,
            quote_currency=quote_currency,
            mapping_notes=mapping_notes
        )
