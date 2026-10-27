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

    def test_matches_schema_fingerprint_message(self):
        classifier = SchemaChangeClassifier()
        exc = ValueError("Schema fingerprint changed")

        result = classifier.classify(exc)

        assert result is not None
        assert result[0] == "schema_change"
        assert "Schema fingerprint" in result[1]

    def test_matches_lowercase_schema(self):
        classifier = SchemaChangeClassifier()
        exc = RuntimeError("database schema mismatch")

        result = classifier.classify(exc)

        assert result is not None
        assert result[0] == "schema_change"
        assert "schema" in result[1]

    def test_does_not_match_unrelated_error(self):
        classifier = SchemaChangeClassifier()
        exc = ValueError("invalid data format")

        result = classifier.classify(exc)

        assert result is None

class TestParseFailureClassifier:

    def test_matches_valueerror(self):
        classifier = ParseFailureClassifier()
        exc = ValueError("invalid literal for int()")

        result = classifier.classify(exc)

        assert result is not None
        assert result[0] == "parse_failure"
        assert "invalid literal" in result[1]

    def test_matches_keyerror(self):
        classifier = ParseFailureClassifier()
        exc = KeyError("missing_key")

        result = classifier.classify(exc)

        assert result is not None
        assert result[0] == "parse_failure"
        assert "missing_key" in result[1]

    def test_matches_attributeerror(self):
        classifier = ParseFailureClassifier()
        exc = AttributeError("'NoneType' object has no attribute 'text'")

        result = classifier.classify(exc)

        assert result is not None
        assert result[0] == "parse_failure"
        assert "text" in result[1]

    def test_does_not_match_other_exceptions(self):
        classifier = ParseFailureClassifier()
        exc = RuntimeError("unexpected error")

        result = classifier.classify(exc)

        assert result is None

class TestHttpFailureClassifier:

    def test_matches_connectionerror(self):
        classifier = HttpFailureClassifier()
        exc = requests.exceptions.ConnectionError("Connection refused")

        result = classifier.classify(exc)

        assert result is not None
        assert result[0] == "http_failure"
        assert "Connection" in result[1]

    def test_matches_timeout(self):
        classifier = HttpFailureClassifier()
        exc = requests.exceptions.Timeout("Read timed out")

        result = classifier.classify(exc)

        assert result is not None
        assert result[0] == "http_failure"
        assert "timed out" in result[1]

    def test_does_not_match_other_exceptions(self):
        classifier = HttpFailureClassifier()
        exc = ValueError("invalid data")

        result = classifier.classify(exc)

        assert result is None

class TestCompositeErrorClassifier:

    def test_returns_first_match(self):
        classifiers = [
            SchemaChangeClassifier(),
            ParseFailureClassifier(),
            HttpFailureClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers)

        exc = ValueError("invalid data")
        result = composite.classify(exc)

        assert result[0] == "parse_failure"

    def test_tries_classifiers_in_order(self):
        classifiers = [
            HttpFailureClassifier(),
            ParseFailureClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers)

        exc = requests.exceptions.ConnectionError("failed")
        result = composite.classify(exc)

        assert result[0] == "http_failure"

    def test_uses_fallback_when_no_match(self):
        classifiers = [
            SchemaChangeClassifier(),
            ParseFailureClassifier(),
            HttpFailureClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers, fallback_code="unknown_error")

        exc = RuntimeError("unexpected error")
        result = composite.classify(exc)

        assert result[0] == "unknown_error"
        assert "RuntimeError" in result[1]
        assert "unexpected error" in result[1]

    def test_default_fallback_is_parse_failure(self):
        classifiers = [HttpFailureClassifier()]
        composite = CompositeErrorClassifier(classifiers)

        exc = ValueError("some error")
        result = composite.classify(exc)

        assert result[0] == "parse_failure"

    def test_always_returns_result(self):
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

    def test_default_classifier_exists(self):
        assert default_classifier is not None
        assert isinstance(default_classifier, CompositeErrorClassifier)

    def test_classifies_schema_change(self):
        exc = ValueError("Schema fingerprint mismatch")
        result = default_classifier.classify(exc)

        assert result[0] == "schema_change"

    def test_classifies_parse_failure(self):
        exc = KeyError("missing_field")
        result = default_classifier.classify(exc)

        assert result[0] == "parse_failure"

    def test_classifies_http_failure(self):
        exc = requests.exceptions.Timeout("timeout")
        result = default_classifier.classify(exc)

        assert result[0] == "http_failure"

    def test_has_fallback(self):
        exc = OSError("disk full")
        result = default_classifier.classify(exc)

        assert result[0] == "parse_failure"
        assert "OSError" in result[1]

class TestClassifierOrdering:

    def test_schema_before_parse(self):
        classifiers = [
            SchemaChangeClassifier(),
            ParseFailureClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers)

        exc = ValueError("schema validation failed")
        result = composite.classify(exc)

        assert result[0] == "schema_change"

    def test_reversed_order_changes_result(self):
        classifiers = [
            ParseFailureClassifier(),
            SchemaChangeClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers)

        exc = ValueError("schema validation failed")
        result = composite.classify(exc)

        assert result[0] == "parse_failure"
