"""
Unit tests for infrastructure.error_classifier module.

Tests the ErrorClassifier strategies including:
- SchemaChangeClassifier matching
- ParseFailureClassifier matching  
- HttpFailureClassifier matching
- CompositeErrorClassifier ordering and fallback
- Default classifier configuration
"""
import pytest
import requests
from infrastructure.error_classifier import (
    ErrorClassifier,
    SchemaChangeClassifier,
    ParseFailureClassifier,
    HttpFailureClassifier,
    CompositeErrorClassifier,
    default_classifier,
)


class TestSchemaChangeClassifier:
    """Test SchemaChangeClassifier strategy."""
    
    def test_matches_schema_fingerprint_message(self):
        """Should match 'Schema fingerprint' in error message."""
        classifier = SchemaChangeClassifier()
        exc = ValueError("Schema fingerprint changed")
        
        result = classifier.classify(exc)
        
        assert result is not None
        assert result[0] == "schema_change"
        assert "Schema fingerprint" in result[1]
    
    def test_matches_lowercase_schema(self):
        """Should match 'schema' keyword (case-insensitive)."""
        classifier = SchemaChangeClassifier()
        exc = RuntimeError("database schema mismatch")
        
        result = classifier.classify(exc)
        
        assert result is not None
        assert result[0] == "schema_change"
        assert "schema" in result[1]
    
    def test_does_not_match_unrelated_error(self):
        """Should return None for non-schema errors."""
        classifier = SchemaChangeClassifier()
        exc = ValueError("invalid data format")
        
        result = classifier.classify(exc)
        
        assert result is None


class TestParseFailureClassifier:
    """Test ParseFailureClassifier strategy."""
    
    def test_matches_valueerror(self):
        """Should match ValueError exceptions."""
        classifier = ParseFailureClassifier()
        exc = ValueError("invalid literal for int()")
        
        result = classifier.classify(exc)
        
        assert result is not None
        assert result[0] == "parse_failure"
        assert "invalid literal" in result[1]
    
    def test_matches_keyerror(self):
        """Should match KeyError exceptions."""
        classifier = ParseFailureClassifier()
        exc = KeyError("missing_key")
        
        result = classifier.classify(exc)
        
        assert result is not None
        assert result[0] == "parse_failure"
        assert "missing_key" in result[1]
    
    def test_matches_attributeerror(self):
        """Should match AttributeError exceptions."""
        classifier = ParseFailureClassifier()
        exc = AttributeError("'NoneType' object has no attribute 'text'")
        
        result = classifier.classify(exc)
        
        assert result is not None
        assert result[0] == "parse_failure"
        assert "text" in result[1]
    
    def test_does_not_match_other_exceptions(self):
        """Should return None for non-parsing exceptions."""
        classifier = ParseFailureClassifier()
        exc = RuntimeError("unexpected error")
        
        result = classifier.classify(exc)
        
        assert result is None


class TestHttpFailureClassifier:
    """Test HttpFailureClassifier strategy."""
    
    def test_matches_connectionerror(self):
        """Should match requests ConnectionError."""
        classifier = HttpFailureClassifier()
        exc = requests.exceptions.ConnectionError("Connection refused")
        
        result = classifier.classify(exc)
        
        assert result is not None
        assert result[0] == "http_failure"
        assert "Connection" in result[1]
    
    def test_matches_timeout(self):
        """Should match requests Timeout."""
        classifier = HttpFailureClassifier()
        exc = requests.exceptions.Timeout("Read timed out")
        
        result = classifier.classify(exc)
        
        assert result is not None
        assert result[0] == "http_failure"
        assert "timed out" in result[1]
    
    def test_does_not_match_other_exceptions(self):
        """Should return None for non-HTTP exceptions."""
        classifier = HttpFailureClassifier()
        exc = ValueError("invalid data")
        
        result = classifier.classify(exc)
        
        assert result is None


class TestCompositeErrorClassifier:
    """Test CompositeErrorClassifier composition and fallback."""
    
    def test_returns_first_match(self):
        """Should return result from first matching classifier."""
        classifiers = [
            SchemaChangeClassifier(),
            ParseFailureClassifier(),
            HttpFailureClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers)
        
        # ValueError should match ParseFailureClassifier
        exc = ValueError("invalid data")
        result = composite.classify(exc)
        
        assert result[0] == "parse_failure"
    
    def test_tries_classifiers_in_order(self):
        """Should try classifiers in the order provided."""
        # Put HttpFailure before ParseFailure
        classifiers = [
            HttpFailureClassifier(),
            ParseFailureClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers)
        
        # ConnectionError should match first classifier
        exc = requests.exceptions.ConnectionError("failed")
        result = composite.classify(exc)
        
        assert result[0] == "http_failure"
    
    def test_uses_fallback_when_no_match(self):
        """Should use fallback code when no classifier matches."""
        classifiers = [
            SchemaChangeClassifier(),
            ParseFailureClassifier(),
            HttpFailureClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers, fallback_code="unknown_error")
        
        # RuntimeError doesn't match any classifier
        exc = RuntimeError("unexpected error")
        result = composite.classify(exc)
        
        assert result[0] == "unknown_error"
        assert "RuntimeError" in result[1]
        assert "unexpected error" in result[1]
    
    def test_default_fallback_is_parse_failure(self):
        """Default fallback should be 'parse_failure'."""
        classifiers = [HttpFailureClassifier()]
        composite = CompositeErrorClassifier(classifiers)
        
        exc = ValueError("some error")
        result = composite.classify(exc)
        
        # ValueError doesn't match HttpFailureClassifier, should use fallback
        assert result[0] == "parse_failure"
    
    def test_always_returns_result(self):
        """CompositeErrorClassifier should always return a result."""
        classifiers = []
        composite = CompositeErrorClassifier(classifiers)
        
        exc = Exception("anything")
        result = composite.classify(exc)
        
        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)


class TestDefaultClassifier:
    """Test the default_classifier module instance."""
    
    def test_default_classifier_exists(self):
        """default_classifier should be initialized."""
        assert default_classifier is not None
        assert isinstance(default_classifier, CompositeErrorClassifier)
    
    def test_classifies_schema_change(self):
        """default_classifier should classify schema changes."""
        exc = ValueError("Schema fingerprint mismatch")
        result = default_classifier.classify(exc)
        
        assert result[0] == "schema_change"
    
    def test_classifies_parse_failure(self):
        """default_classifier should classify parse failures."""
        exc = KeyError("missing_field")
        result = default_classifier.classify(exc)
        
        assert result[0] == "parse_failure"
    
    def test_classifies_http_failure(self):
        """default_classifier should classify HTTP failures."""
        exc = requests.exceptions.Timeout("timeout")
        result = default_classifier.classify(exc)
        
        assert result[0] == "http_failure"
    
    def test_has_fallback(self):
        """default_classifier should have fallback for unknown errors."""
        exc = OSError("disk full")
        result = default_classifier.classify(exc)
        
        # Should classify as parse_failure (fallback)
        assert result[0] == "parse_failure"
        assert "OSError" in result[1]


class TestClassifierOrdering:
    """Test that classifier order affects results."""
    
    def test_schema_before_parse(self):
        """Schema classifier should match before parse classifier."""
        # A ValueError with "schema" keyword should match schema first
        classifiers = [
            SchemaChangeClassifier(),
            ParseFailureClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers)
        
        exc = ValueError("schema validation failed")
        result = composite.classify(exc)
        
        # Should match SchemaChangeClassifier, not ParseFailureClassifier
        assert result[0] == "schema_change"
    
    def test_reversed_order_changes_result(self):
        """Reversing order should change classification result."""
        # Put ParseFailure before Schema
        classifiers = [
            ParseFailureClassifier(),
            SchemaChangeClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers)
        
        exc = ValueError("schema validation failed")
        result = composite.classify(exc)
        
        # Should match ParseFailureClassifier first
        assert result[0] == "parse_failure"
