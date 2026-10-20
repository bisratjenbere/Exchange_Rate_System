"""
Error Classifier using Strategy Pattern for extensible error handling.

This module provides the Strategy Pattern for error classification,
replacing if-else chains with composable, testable strategies.
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import requests


class ErrorClassifier(ABC):
    """
    Abstract base for error classification strategies.
    
    Strategy Pattern: Each classifier knows how to identify one error type.
    Replaces lengthy if-else chains with composable, testable strategies.
    
    Benefits:
        - Open/Closed: Add new classifiers without modifying existing code
        - Single Responsibility: Each classifier knows one error type
        - Testable: Test each classifier in isolation
        - Composable: Combine classifiers via Composite pattern
    
    Example:
        >>> class CustomClassifier(ErrorClassifier):
        ...     def classify(self, exc):
        ...         if "custom error" in str(exc):
        ...             return ("custom_error", str(exc))
        ...         return None
    """
    
    @abstractmethod
    def classify(self, exc: Exception) -> Optional[Tuple[str, str]]:
        """
        Classify an exception into (error_code, error_summary).
        
        Args:
            exc: The exception to classify
        
        Returns:
            (error_code, error_summary) if this classifier matches
            None if this classifier doesn't recognize the exception
        
        Example:
            >>> classifier = SchemaChangeClassifier()
            >>> exc = ValueError("Schema fingerprint changed")
            >>> result = classifier.classify(exc)
            >>> result
            ('schema_change', 'Schema fingerprint changed')
        """
        pass


class SchemaChangeClassifier(ErrorClassifier):
    """
    Detects schema fingerprint changes.
    
    Matches exceptions containing "Schema fingerprint" or "schema" keyword.
    Used when the adapter's HTML/JSON structure changes unexpectedly.
    """
    
    def classify(self, exc: Exception) -> Optional[Tuple[str, str]]:
        """
        Classify schema change errors.
        
        Args:
            exc: Exception to check
        
        Returns:
            ("schema_change", message) if schema-related
            None otherwise
        """
        msg = str(exc)
        if "Schema fingerprint" in msg or "schema" in msg.lower():
            return ("schema_change", msg)
        return None


class ParseFailureClassifier(ErrorClassifier):
    """
    Detects parsing errors (ValueError, KeyError, AttributeError).
    
    Matches exceptions that occur during adapter.parse() when the
    HTML/JSON structure doesn't match expectations.
    """
    
    def classify(self, exc: Exception) -> Optional[Tuple[str, str]]:
        """
        Classify parsing errors.
        
        Args:
            exc: Exception to check
        
        Returns:
            ("parse_failure", message) if parsing-related
            None otherwise
        """
        if isinstance(exc, (ValueError, KeyError, AttributeError)):
            msg = str(exc)
            return ("parse_failure", msg)
        return None


class HttpFailureClassifier(ErrorClassifier):
    """
    Detects network/HTTP errors.
    
    Matches ConnectionError and Timeout exceptions from the requests library.
    Used when the bank website is unreachable or slow to respond.
    """
    
    def classify(self, exc: Exception) -> Optional[Tuple[str, str]]:
        """
        Classify HTTP/network errors.
        
        Args:
            exc: Exception to check
        
        Returns:
            ("http_failure", message) if network-related
            None otherwise
        """
        if isinstance(exc, (requests.exceptions.ConnectionError,
                           requests.exceptions.Timeout)):
            msg = str(exc)
            return ("http_failure", msg)
        return None


class CompositeErrorClassifier(ErrorClassifier):
    """
    Composite classifier that tries multiple strategies in order.
    
    First matching classifier wins. If none match, returns fallback.
    
    This implements the Composite pattern, allowing multiple classifiers
    to be combined into a single classification pipeline.
    
    Example:
        >>> classifiers = [
        ...     SchemaChangeClassifier(),
        ...     ParseFailureClassifier(),
        ...     HttpFailureClassifier(),
        ... ]
        >>> composite = CompositeErrorClassifier(classifiers)
        >>> error_code, msg = composite.classify(some_exception)
    """
    
    def __init__(self, classifiers: list[ErrorClassifier], 
                 fallback_code: str = "parse_failure"):
        """
        Initialize composite classifier.
        
        Args:
            classifiers: List of classifiers to try in order
            fallback_code: Error code to use when no classifier matches
                          (default: "parse_failure")
        """
        self.classifiers = classifiers
        self.fallback_code = fallback_code
    
    def classify(self, exc: Exception) -> Tuple[str, str]:
        """
        Always returns a result (uses fallback if no match).
        
        Tries each classifier in order until one returns a non-None result.
        If all classifiers return None, uses the fallback error code.
        
        Args:
            exc: Exception to classify
        
        Returns:
            (error_code, error_summary) - always returns a result
        
        Example:
            >>> composite.classify(ValueError("invalid data"))
            ('parse_failure', 'invalid data')
            
            >>> composite.classify(requests.exceptions.Timeout())
            ('http_failure', 'Connection timeout')
        """
        for classifier in self.classifiers:
            result = classifier.classify(exc)
            if result is not None:
                return result
        
        # Fallback - always return a classification
        msg = f"{type(exc).__name__}: {str(exc)}"
        return (self.fallback_code, msg)


# Default classifier with all strategies registered
# Order matters: specific classifiers before general ones
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
