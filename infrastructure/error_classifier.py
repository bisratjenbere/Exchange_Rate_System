from abc import ABC, abstractmethod
from typing import Optional, Tuple
import requests

class ErrorClassifier(ABC):

    @abstractmethod
    def classify(self, exc: Exception) -> Optional[Tuple[str, str]]:
        pass

class SchemaChangeClassifier(ErrorClassifier):

    def classify(self, exc: Exception) -> Optional[Tuple[str, str]]:
        msg = str(exc)
        if "Schema fingerprint" in msg or "schema" in msg.lower():
            return ("schema_change", msg)
        return None

class ParseFailureClassifier(ErrorClassifier):

    def classify(self, exc: Exception) -> Optional[Tuple[str, str]]:
        if isinstance(exc, (ValueError, KeyError, AttributeError)):
            msg = str(exc)
            return ("parse_failure", msg)
        return None

class HttpFailureClassifier(ErrorClassifier):

    def classify(self, exc: Exception) -> Optional[Tuple[str, str]]:
        if isinstance(exc, (requests.exceptions.ConnectionError,
                           requests.exceptions.Timeout)):
            msg = str(exc)
            return ("http_failure", msg)
        return None

class CompositeErrorClassifier(ErrorClassifier):

    def __init__(self, classifiers: list[ErrorClassifier],
                 fallback_code: str = "parse_failure"):
        self.classifiers = classifiers
        self.fallback_code = fallback_code

    def classify(self, exc: Exception) -> Tuple[str, str]:
        for classifier in self.classifiers:
            result = classifier.classify(exc)
            if result is not None:
                return result

        msg = f"{type(exc).__name__}: {str(exc)}"
        return (self.fallback_code, msg)

default_classifier = CompositeErrorClassifier([
    SchemaChangeClassifier(),
    ParseFailureClassifier(),
    HttpFailureClassifier(),
])
"""
Default error classifier instance with all strategies.

This is the recommended classifier for most use cases. It tries
classifiers in order of specificity:
1. SchemaChangeClassifier - most specific
2. ParseFailureClassifier - medium specificity
3. HttpFailureClassifier - medium specificity
4. Fallback to "parse_failure" - least specific

Example:
    >>> from infrastructure.error_classifier import default_classifier
    >>> error_code, msg = default_classifier.classify(exception)
"""
