"""
Configuration parser and validator for field detection.

Provides validation and pretty-printing for field detection configurations.
"""

import json
from typing import Dict, Any
from pipeline.category_normalizer import validate_category


def parse_field_config(config_dict: dict) -> dict:
    """
    Parse and validate field configuration.
    
    Args:
        config_dict: Configuration dictionary
    
    Returns:
        Validated configuration dict
    
    Raises:
        ValueError: If configuration is invalid
    """
    if not isinstance(config_dict, dict):
        raise ValueError("Configuration must be a dictionary")
    
    validated = {}
    
    # Validate field_mappings
    if "field_mappings" in config_dict:
        mappings = config_dict["field_mappings"]
        if not isinstance(mappings, dict):
            raise ValueError("field_mappings must be a dict")
        
        for field, category in mappings.items():
            if not isinstance(field, str) or not isinstance(category, str):
                raise ValueError(f"Invalid mapping: {field} → {category}")
            if not validate_category(category) and category != "UNKNOWN":
                raise ValueError(f"Invalid category: {category}")
        
        validated["field_mappings"] = mappings
    
    # Validate default_category
    if "default_category" in config_dict:
        default = config_dict["default_category"]
        if not isinstance(default, str):
            raise ValueError(f"default_category must be a string, got {type(default)}")
        if not validate_category(default) and default != "UNKNOWN":
            raise ValueError(f"Invalid default_category: {default}")
        validated["default_category"] = default
    
    # Pass through field_patterns (validated at runtime)
    if "field_patterns" in config_dict:
        validated["field_patterns"] = config_dict["field_patterns"]
    
    return validated


def print_field_config(config_dict: dict) -> str:
    """
    Pretty-print field configuration for readability.
    
    Args:
        config_dict: Configuration dictionary
    
    Returns:
        Formatted JSON string
    """
    return json.dumps(config_dict, indent=2, sort_keys=True)
