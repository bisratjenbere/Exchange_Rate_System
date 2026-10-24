"""
RecordEmitter: Creates AdapterRecord objects from field pairs.

This module implements the No-Data-Loss Principle: when a bank API publishes
structurally distinct field pairs, the system emits one record per field pair,
even if values are numerically identical.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate
from .detector import FieldPair
from .mapper import CategoryMapper


class RecordEmitter:
    """Creates AdapterRecords from field pairs and raw data."""
    
    def emit_records_from_fields(
        self,
        data: dict,
        field_pairs: List[FieldPair],
        category_mapper: CategoryMapper,
        *,
        # Required AdapterRecord fields
        currency: str,
        effective_date: Optional[date] = None,
        effective_date_basis: str = "collection_date_fallback",
        source_record_id: Optional[str] = None,
        source_publication_id: Optional[str] = None,
        unit_multiplier: int = 1,
        # Optional fields
        currency_name: Optional[str] = None,
        quote_currency: Optional[str] = None,
        mapping_notes: Optional[List[str]] = None
    ) -> List[AdapterRecord]:
        """
        Emit one AdapterRecord per field pair.
        
        Args:
            data: Raw dict containing rate fields
            field_pairs: List of detected field pairs
            category_mapper: CategoryMapper for field-to-category mapping
            currency: Source currency code (e.g., "USD")
            effective_date: Effective date from source
            effective_date_basis: Date basis indicator
            source_record_id: Base source record key (will append category)
            source_publication_id: Publication key
            unit_multiplier: Unit multiplier
            currency_name: Optional currency name
            quote_currency: Optional quote currency
            mapping_notes: Optional mapping notes
        
        Returns:
            List of AdapterRecord objects (one per field pair)
        
        Example:
            data = {"buying": 162.00, "tra_buying": 162.00,
                    "selling": 165.00, "tra_selling": 165.00}
            pairs = [FieldPair("buying", "selling"),
                     FieldPair("tra_buying", "tra_selling")]
            
            records = emitter.emit_records_from_fields(
                data, pairs, mapper,
                currency="USD",
                source_record_id="123"
            )
            # Returns: [
            #   AdapterRecord(currency="USD", category="cash", 
            #                 buying_rate=162.00, source_record_key="123:cash"),
            #   AdapterRecord(currency="USD", category="transactional",
            #                 buying_rate=162.00, source_record_key="123:transactional")
            # ]
        """
        records = []
        
        for pair in field_pairs:
            # Extract rates from data
            buying_raw = data.get(pair.buy_field)
            selling_raw = data.get(pair.sell_field)
            
            # Skip if both rates are None/null
            buying_rate = self._safe_rate(buying_raw)
            selling_rate = self._safe_rate(selling_raw)
            if buying_rate is None and selling_rate is None:
                continue
            
            # Map field to category
            category = category_mapper.map_field_pair(pair)
            
            # Generate unique source_record_key with category suffix
            if source_record_id and len(field_pairs) > 1:
                src_key = f"{source_record_id}:{category}"
            else:
                src_key = source_record_id
            
            # Build mapping notes
            notes = (mapping_notes or []).copy()
            notes.append(f"field_structure:{pair.buy_field}/{pair.sell_field}")
            notes.append(f"category_detected:{category}")
            
            # Create record
            record = AdapterRecord(
                source_currency_code=currency,
                currency_name=currency_name,
                category=category,
                buying_rate=buying_rate,
                selling_rate=selling_rate,
                source_rate_text=f"{buying_raw}/{selling_raw}",
                effective_date=effective_date,
                effective_date_basis=effective_date_basis,
                source_record_key=src_key,
                source_publication_key=source_publication_id,
                quote_currency_code=quote_currency,
                unit_multiplier=unit_multiplier,
                raw_excerpt={
                    "original_id": source_record_id,
                    "field_pair": str(pair),
                    pair.buy_field: buying_raw,
                    pair.sell_field: selling_raw
                },
                mapping_notes=notes
            )
            records.append(record)
        
        return records
    
    @staticmethod
    def _safe_rate(raw) -> Optional[Decimal]:
        """Safely convert raw value to Decimal rate."""
        try:
            return normalize_rate(raw)
        except (ValueError, TypeError):
            return None
