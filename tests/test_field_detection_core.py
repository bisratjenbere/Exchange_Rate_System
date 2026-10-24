"""
Unit tests for field detection core components.

Tests FieldDetector, CategoryMapper, and RecordEmitter independently.
"""

import pytest
from decimal import Decimal
from datetime import date

from field_detection.detector import FieldDetector, FieldPair
from field_detection.mapper import CategoryMapper
from field_detection.emitter import RecordEmitter


class TestFieldDetector:
    """Test FieldDetector component."""
    
    def test_detect_cbe_pattern(self):
        """Test CBE pattern (explicit categories)."""
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
        """Test Wegagen pattern (prefix convention)."""
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
        """Test Rammis pattern (single pair)."""
        detector = FieldDetector()
        data = {"buying": 162.00, "selling": 165.00}
        
        pairs = detector.detect_field_pairs(data)
        
        assert len(pairs) == 1
        assert pairs[0].buy_field == "buying"
        assert pairs[0].sell_field == "selling"
    
    def test_skip_incomplete_pairs(self):
        """Test that incomplete pairs are skipped."""
        detector = FieldDetector()
        data = {"buying": 162.00, "tra_selling": 165.00}
        
        pairs = detector.detect_field_pairs(data)
        
        assert len(pairs) == 0
    
    def test_empty_data(self):
        """Test empty data returns empty list."""
        detector = FieldDetector()
        
        assert detector.detect_field_pairs({}) == []
        assert detector.detect_field_pairs(None) == []


class TestCategoryMapper:
    """Test CategoryMapper component."""
    
    def test_explicit_category_fields(self):
        """Test explicit category field names."""
        mapper = CategoryMapper()
        
        assert mapper.map_field_to_category("cashBuying") == "cash"
        assert mapper.map_field_to_category("transactionalBuying") == "transactional"
    
    def test_prefix_patterns(self):
        """Test prefix patterns."""
        mapper = CategoryMapper()
        
        assert mapper.map_field_to_category("tra_buying") == "transactional"
        assert mapper.map_field_to_category("cash_buying") == "cash"
    
    def test_default_category(self):
        """Test ambiguous fields use default category."""
        mapper = CategoryMapper(default_category="transactional")
        
        assert mapper.map_field_to_category("buying") == "transactional"
    
    def test_explicit_mappings_override(self):
        """Test explicit field mappings override defaults."""
        mapper = CategoryMapper(field_mappings={"buying": "cash"})
        
        assert mapper.map_field_to_category("buying") == "cash"
    
    def test_map_field_pair(self):
        """Test mapping a field pair uses buying field."""
        mapper = CategoryMapper(field_mappings={"buying": "cash"})
        pair = FieldPair("buying", "selling")
        
        assert mapper.map_field_pair(pair) == "cash"


class TestRecordEmitter:
    """Test RecordEmitter component."""
    
    def test_emit_multiple_categories(self):
        """Test multiple categories from same source item."""
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
        # Records can be in any order, so check by category
        categories = {r.category for r in records}
        assert categories == {"cash", "transactional"}
        # Check source_record_key format
        for record in records:
            assert record.source_record_key.startswith("123:")
            assert record.category in record.source_record_key
    
    def test_emit_single_category_no_suffix(self):
        """Test single category has no suffix in key."""
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
        """Test pairs with no rates are skipped."""
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
        """Test metadata is included in record."""
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
