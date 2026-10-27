from datetime import date
from typing import List, Optional

from domain.records import AdapterRecord
from .detector import FieldDetector
from .mapper import CategoryMapper
from .emitter import RecordEmitter

class FieldStructureMixin:

    FIELD_CONFIG: dict = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._detector = None
        self._mapper = None
        self._emitter = None

    @property
    def field_detector(self) -> FieldDetector:
        if self._detector is None:
            config = self.FIELD_CONFIG
            field_patterns = config.get("field_patterns")
            self._detector = FieldDetector(field_patterns=field_patterns)
        return self._detector

    @property
    def category_mapper(self) -> CategoryMapper:
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
        field_pairs = self.field_detector.detect_field_pairs(data)

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
