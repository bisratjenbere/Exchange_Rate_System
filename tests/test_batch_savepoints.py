"""
Tests for batch savepoint optimization in pipeline/ingest.py

Verifies that:
1. Batch processing functions exist and are callable
2. Constants are defined correctly
3. Basic smoke tests for the new code paths
"""

import pytest
from pipeline.ingest import (
    ingest,
    _process_batch_optimistic,
    _process_batch_individually,
    IngestResult,
    SAVEPOINT_BATCH_SIZE
)


class TestBatchSavepointConstants:
    """Test batch savepoint constants and configuration"""
    
    def test_batch_size_constant_defined(self):
        """Verify batch size is defined and reasonable"""
        assert SAVEPOINT_BATCH_SIZE == 10
        assert isinstance(SAVEPOINT_BATCH_SIZE, int)
        assert SAVEPOINT_BATCH_SIZE > 0


class TestBatchFunctionsExist:
    """Test that batch processing functions exist and are callable"""
    
    def test_process_batch_optimistic_exists(self):
        """Verify _process_batch_optimistic function exists"""
        assert callable(_process_batch_optimistic)
    
    def test_process_batch_individually_exists(self):
        """Verify _process_batch_individually function exists"""
        assert callable(_process_batch_individually)
    
    def test_ingest_function_signature(self):
        """Verify ingest function has correct signature"""
        import inspect
        sig = inspect.signature(ingest)
        params = list(sig.parameters.keys())
        
        assert 'conn' in params
        assert 'records' in params
        assert 'source_id' in params
        assert 'run_id' in params


class TestIngestResultStructure:
    """Test IngestResult structure is preserved"""
    
    def test_ingest_result_fields(self):
        """Verify IngestResult has all expected fields"""
        result = IngestResult()
        
        assert hasattr(result, 'accepted')
        assert hasattr(result, 'flagged')
        assert hasattr(result, 'rejected')
        assert hasattr(result, 'duplicates')
        assert hasattr(result, 'candidates')
        assert hasattr(result, 'errors')
        assert hasattr(result, 'suspicious')
        
        # Verify default values
        assert result.accepted == 0
        assert result.flagged == 0
        assert result.rejected == 0
        assert result.duplicates == 0
        assert result.candidates == 0
        assert isinstance(result.errors, list)
        assert result.suspicious is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

