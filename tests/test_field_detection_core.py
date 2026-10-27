import pytest
from decimal import Decimal
from datetime import date

from field_detection.detector import FieldDetector, FieldPair
from field_detection.mapper import CategoryMapper
from field_detection.emitter import RecordEmitter

class TestFieldDetector:

    def test_detect_cbe_pattern(self):
        detector = FieldDetector()
        data = {
            "cashBuying": 162.00,
            "cashSelling": 165.00,
            "transactionalBuying": 162.00,
            "transactionalSelling": 165.00
        }

        pairs = detector.detect_field_pairs(data)

        assert len(pairs) == 2
        assert pairs[0].buy_field == "cashBuying"
        assert pairs[0].sell_field == "cashSelling"
        assert pairs[1].buy_field == "transactionalBuying"
        assert pairs[1].sell_field == "transactionalSelling"

    def test_detect_wegagen_pattern(self):
        detector = FieldDetector()
        data = {
            "buying": 162.00,
            "selling": 165.00,
            "tra_buying": 162.00,
            "tra_selling": 165.00
        }

        pairs = detector.detect_field_pairs(data)

        assert len(pairs) == 2

    def test_detect_rammis_pattern(self):
        detector = FieldDetector()
        data = {"buying": 162.00, "selling": 165.00}

        pairs = detector.detect_field_pairs(data)

        assert len(pairs) == 1
        assert pairs[0].buy_field == "buying"
        assert pairs[0].sell_field == "selling"

    def test_detect_awash_pattern(self):
        detector = FieldDetector()
        data = {
            "buying": "161.0539",
            "selling": "164.2750",
            "transaction_buying": "161.0539",
            "transaction_selling": "164.2750",
            "weighted_buying_average": "163.8680",
            "weighted_selling_average": "164.2653",
        }
        pairs = detector.detect_field_pairs(data)
        assert len(pairs) == 3
        fields = {(p.buy_field, p.sell_field) for p in pairs}
        assert ("weighted_buying_average", "weighted_selling_average") in fields
        assert ("transaction_buying", "transaction_selling") in fields
        assert ("buying", "selling") in fields

    def test_awash_adapter_parsing(self):
        from adapters.awash.adapter import AwashAdapter
        import json
        adapter = AwashAdapter()
        payload = json.dumps({
            "success": True,
            "data": {
                "date": "2026-10-26",
                "rates": {
                    "USD": {
                        "buying": "161.0539",
                        "selling": "164.2750",
                        "transaction_buying": "161.0539",
                        "transaction_selling": "164.2750",
                        "weighted_buying_average": "163.8680",
                        "weighted_selling_average": "164.2653",
                    }
                }
            }
        })
        res = adapter.parse(payload)
        assert len(res.records) == 3
        cats = {r.category for r in res.records}
        assert cats == {"cash", "transactional", "weighted_average"}

    def test_skip_incomplete_pairs(self):
        detector = FieldDetector()
        data = {"buying": 162.00, "tra_selling": 165.00}

        pairs = detector.detect_field_pairs(data)

        assert len(pairs) == 0

    def test_empty_data(self):
        detector = FieldDetector()

        assert detector.detect_field_pairs({}) == []
        assert detector.detect_field_pairs(None) == []

class TestCategoryMapper:

    def test_explicit_category_fields(self):
        mapper = CategoryMapper()

        assert mapper.map_field_to_category("cashBuying") == "cash"
        assert mapper.map_field_to_category("transactionalBuying") == "transactional"

    def test_prefix_patterns(self):
        mapper = CategoryMapper()

        assert mapper.map_field_to_category("tra_buying") == "transactional"
        assert mapper.map_field_to_category("cash_buying") == "cash"

    def test_default_category(self):
        mapper = CategoryMapper(default_category="transactional")

        assert mapper.map_field_to_category("buying") == "transactional"

    def test_explicit_mappings_override(self):
        mapper = CategoryMapper(field_mappings={"buying": "cash"})

        assert mapper.map_field_to_category("buying") == "cash"

    def test_map_field_pair(self):
        mapper = CategoryMapper(field_mappings={"buying": "cash"})
        pair = FieldPair("buying", "selling")

        assert mapper.map_field_pair(pair) == "cash"

class TestRecordEmitter:

    def test_emit_multiple_categories(self):
        detector = FieldDetector()
        mapper = CategoryMapper(field_mappings={
            "buying": "cash",
            "tra_buying": "transactional"
        })
        emitter = RecordEmitter()

        data = {
            "buying": 162.00,
            "tra_buying": 162.00,
            "selling": 165.00,
            "tra_selling": 165.00
        }
        pairs = detector.detect_field_pairs(data)

        records = emitter.emit_records_from_fields(
            data, pairs, mapper,
            currency="USD",
            source_record_id="123"
        )

        assert len(records) == 2
        categories = {r.category for r in records}
        assert categories == {"cash", "transactional"}
        for record in records:
            assert record.source_record_key.startswith("123:")
            assert record.category in record.source_record_key

    def test_emit_single_category_no_suffix(self):
        detector = FieldDetector()
        mapper = CategoryMapper(field_mappings={"buying": "cash"})
        emitter = RecordEmitter()

        data = {"buying": 162.00, "selling": 165.00}
        pairs = detector.detect_field_pairs(data)

        records = emitter.emit_records_from_fields(
            data, pairs, mapper,
            currency="USD",
            source_record_id="456"
        )

        assert len(records) == 1
        assert records[0].source_record_key == "456"

    def test_skip_pairs_with_no_rates(self):
        detector = FieldDetector()
        mapper = CategoryMapper(field_mappings={
            "buying": "cash",
            "tra_buying": "transactional"
        })
        emitter = RecordEmitter()

        data = {
            "buying": None,
            "selling": None,
            "tra_buying": 162.00,
            "tra_selling": 165.00
        }
        pairs = detector.detect_field_pairs(data)

        records = emitter.emit_records_from_fields(
            data, pairs, mapper,
            currency="USD",
            source_record_id="789"
        )

        assert len(records) == 1
        assert records[0].category == "transactional"

    def test_metadata_in_record(self):
        detector = FieldDetector()
        mapper = CategoryMapper(field_mappings={"buying": "cash"})
        emitter = RecordEmitter()

        data = {"buying": 162.00, "selling": 165.00}
        pairs = detector.detect_field_pairs(data)

        records = emitter.emit_records_from_fields(
            data, pairs, mapper,
            currency="USD",
            source_record_id="123"
        )

        assert len(records) == 1
        record = records[0]
        assert "field_structure:buying/selling" in record.mapping_notes
        assert "category_detected:cash" in record.mapping_notes
        assert record.raw_excerpt["field_pair"] == "(buying, selling)"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
