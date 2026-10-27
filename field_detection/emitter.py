from datetime import date
from decimal import Decimal
from typing import List, Optional

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate
from .detector import FieldPair
from .mapper import CategoryMapper

class RecordEmitter:

    def emit_records_from_fields(
        self,
        data: dict,
        field_pairs: List[FieldPair],
        category_mapper: CategoryMapper,
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
        records = []

        for pair in field_pairs:
            buying_raw = data.get(pair.buy_field)
            selling_raw = data.get(pair.sell_field)

            buying_rate = self._safe_rate(buying_raw)
            selling_rate = self._safe_rate(selling_raw)
            if buying_rate is None and selling_rate is None:
                continue

            category = category_mapper.map_field_pair(pair)

            if source_record_id and len(field_pairs) > 1:
                src_key = f"{source_record_id}:{category}"
            else:
                src_key = source_record_id

            notes = (mapping_notes or []).copy()
            notes.append(f"field_structure:{pair.buy_field}/{pair.sell_field}")
            notes.append(f"category_detected:{category}")

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
        try:
            return normalize_rate(raw)
        except (ValueError, TypeError):
            return None
