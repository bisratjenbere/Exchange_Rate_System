"""
Infrastructure components for the Exchange Rate System.

This package provides foundational infrastructure patterns:
- Config: Centralized configuration management
- AdapterRegistry: Type-safe adapter registration and lookup
- RateSourceRepository: Repository pattern for database operations
- ErrorClassifier: Strategy pattern for error classification
"""

from infrastructure.config import Config
from infrastructure.adapter_registry import AdapterRegistry, default_registry
from infrastructure.rate_source_repository import RateSourceRepository
from infrastructure.error_classifier import (
    ErrorClassifier,
    SchemaChangeClassifier,
    ParseFailureClassifier,
    HttpFailureClassifier,
    CompositeErrorClassifier,
    default_classifier,
)

__all__ = [
    "Config",
    "AdapterRegistry",
    "default_registry",
    "RateSourceRepository",
    "ErrorClassifier",
    "SchemaChangeClassifier",
    "ParseFailureClassifier",
    "HttpFailureClassifier",
    "CompositeErrorClassifier",
    "default_classifier",
]
