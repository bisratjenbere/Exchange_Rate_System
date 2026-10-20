"""
Adapter Registry for type-safe adapter registration and lookup.

This module provides the AdapterRegistry pattern that replaces importlib
string manipulation with explicit, type-safe adapter registration.
"""
from typing import Any

# Import all adapter modules
from adapters.abay import adapter as abay_adapter
from adapters.adib import adapter as adib_adapter
from adapters.ahadu import adapter as ahadu_adapter
from adapters.amhara import adapter as amhara_adapter
from adapters.anbesa import adapter as anbesa_adapter
from adapters.awash import adapter as awash_adapter
from adapters.berhan import adapter as berhan_adapter
from adapters.boa import adapter as boa_adapter
from adapters.bunna import adapter as bunna_adapter
from adapters.cbe import adapter as cbe_adapter
from adapters.cbo import adapter as cbo_adapter
from adapters.dashen import adapter as dashen_adapter
from adapters.dbe import adapter as dbe_adapter
from adapters.enat import adapter as enat_adapter
from adapters.gadaa import adapter as gadaa_adapter
from adapters.global_ import adapter as global_adapter
from adapters.goh_betoch import adapter as goh_betoch_adapter
from adapters.hibret import adapter as hibret_adapter
from adapters.nib import adapter as nib_adapter
from adapters.omo import adapter as omo_adapter
from adapters.oromia import adapter as oromia_adapter
from adapters.rammis import adapter as rammis_adapter
from adapters.shabelle import adapter as shabelle_adapter
from adapters.sidama import adapter as sidama_adapter
from adapters.siinqee import adapter as siinqee_adapter
from adapters.siket import adapter as siket_adapter
from adapters.tsedey import adapter as tsedey_adapter
from adapters.tsehay import adapter as tsehay_adapter
from adapters.wegagen import adapter as wegagen_adapter
from adapters.zamzam import adapter as zamzam_adapter
from adapters.zemen import adapter as zemen_adapter


class AdapterRegistry:
    """
    Central registry for explicit adapter registration and lookup.
    
    Replaces the importlib string manipulation trial-and-error logic
    in _load_adapter() with explicit, type-safe registration.
    
    Benefits:
        - Type-safe: No runtime string manipulation errors
        - Fail-fast: Import errors caught at module load, not runtime
        - Clear errors: Shows all available adapters when key not found
        - IDE-friendly: Autocomplete works for adapter imports
        - Testable: Can create mock registries for testing
    
    Example:
        >>> registry = AdapterRegistry()
        >>> registry.register("cbe_api", cbe_adapter)
        >>> adapter = registry.get("cbe_api")
        >>> adapter.parse(raw_html)
        
        >>> # Check availability
        >>> registry.is_registered("dashen_html")
        True
        
        >>> # List all adapters
        >>> registry.list_keys()
        ['abay_html', 'adib_api', 'ahadu_html', ...]
    """
    
    def __init__(self):
        """Initialize an empty adapter registry."""
        self._adapters: dict[str, Any] = {}
    
    def register(self, adapter_key: str, adapter_module: Any) -> None:
        """
        Register an adapter module by adapter_key.
        
        Args:
            adapter_key: Unique key for the adapter (e.g., "cbe_api", 
                        "dashen_html", "global_html")
            adapter_module: The imported adapter module containing parse(),
                           schema_fingerprint(), etc.
        
        Raises:
            ValueError: If adapter_key is already registered
        
        Example:
            >>> from adapters.cbe import adapter as cbe_adapter
            >>> registry.register("cbe_api", cbe_adapter)
        """
        if adapter_key in self._adapters:
            raise ValueError(
                f"Adapter {adapter_key!r} already registered. "
                f"Cannot register the same adapter key twice."
            )
        self._adapters[adapter_key] = adapter_module
    
    def get(self, adapter_key: str) -> Any:
        """
        Get adapter module by adapter_key.
        
        Args:
            adapter_key: The adapter key to look up (e.g., "cbe_api")
        
        Returns:
            The adapter module with parse(), schema_fingerprint(), etc.
        
        Raises:
            KeyError: If adapter_key is not registered. The error message
                     includes the list of all available adapters.
        
        Example:
            >>> adapter = registry.get("cbe_api")
            >>> records = adapter.parse(raw_html)
        """
        if adapter_key not in self._adapters:
            available = ', '.join(sorted(self._adapters.keys()))
            raise KeyError(
                f"Adapter {adapter_key!r} not registered. "
                f"Available adapters: {available}"
            )
        return self._adapters[adapter_key]
    
    def list_keys(self) -> list[str]:
        """
        Return list of all registered adapter keys.
        
        Returns:
            Sorted list of all adapter keys in the registry
        
        Example:
            >>> registry.list_keys()
            ['abay_html', 'adib_api', 'ahadu_html', ...]
        """
        return sorted(self._adapters.keys())
    
    def is_registered(self, adapter_key: str) -> bool:
        """
        Check if adapter_key is registered.
        
        Args:
            adapter_key: The adapter key to check
        
        Returns:
            True if adapter_key is registered, False otherwise
        
        Example:
            >>> registry.is_registered("cbe_api")
            True
            >>> registry.is_registered("nonexistent_adapter")
            False
        """
        return adapter_key in self._adapters


# Default global registry with all 31 adapters explicitly registered
default_registry = AdapterRegistry()

# Explicit registration (replaces importlib trial-and-error)
# This fails at import time if any adapter module is missing,
# rather than failing later at runtime when the adapter is needed.

default_registry.register("abay_html", abay_adapter)
default_registry.register("adib_api", adib_adapter)
default_registry.register("ahadu_html", ahadu_adapter)
default_registry.register("amhara_html", amhara_adapter)
default_registry.register("anbesa_browser", anbesa_adapter)
default_registry.register("awash_ajax", awash_adapter)
default_registry.register("berhan_html", berhan_adapter)
default_registry.register("boa_html", boa_adapter)
default_registry.register("bunna_html", bunna_adapter)
default_registry.register("cbe_api", cbe_adapter)
default_registry.register("cbo_html", cbo_adapter)
default_registry.register("dashen_html", dashen_adapter)
default_registry.register("dbe_html", dbe_adapter)
default_registry.register("enat_html", enat_adapter)
default_registry.register("gadaa_api", gadaa_adapter)
default_registry.register("global_html", global_adapter)
default_registry.register("goh_betoch_html", goh_betoch_adapter)
default_registry.register("hibret_html", hibret_adapter)
default_registry.register("nib_html", nib_adapter)
default_registry.register("omo_html", omo_adapter)
default_registry.register("oromia_html", oromia_adapter)
default_registry.register("rammis_api", rammis_adapter)
default_registry.register("shabelle_html", shabelle_adapter)
default_registry.register("sidama_html", sidama_adapter)
default_registry.register("siinqee_html", siinqee_adapter)
default_registry.register("siket_html", siket_adapter)
default_registry.register("tsedey_html", tsedey_adapter)
default_registry.register("tsehay_html", tsehay_adapter)
default_registry.register("wegagen_api", wegagen_adapter)
default_registry.register("zamzam_html", zamzam_adapter)
default_registry.register("zemen_ajax", zemen_adapter)
