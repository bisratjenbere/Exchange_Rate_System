"""
Field-structure-based category detection for exchange rate adapters.

This package provides components for automatically detecting exchange rate
categories from JSON field structures, following the No-Data-Loss Principle:
when a bank API publishes structurally distinct field pairs, the system
emits one record per field pair.
"""

from .detector import FieldDetector, FieldPair
from .mapper import CategoryMapper
from .emitter import RecordEmitter
from .mixin import FieldStructureMixin

__all__ = [
    "FieldDetector",
    "FieldPair",
    "CategoryMapper",
    "RecordEmitter",
    "FieldStructureMixin",
]
