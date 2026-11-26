"""
Adapter Registry V2 - Clean architecture adapter registry

Supports:
- Clean adapters implementing UniversalAdapter protocol
- Type-safe with protocol checking
- Simple registration and lookup

Design:
- Stores adapter instances (not modules)
- Validates adapters on registration
- Protocol-based type safety

Usage:
    # Register adapter
    from adapters.banks.cbe_new import ADAPTER
    registry.register("cbe_api", ADAPTER)
    
    # Get adapter
    adapter = registry.get("cbe_api")
    outcome = adapter.parse(raw, ctx)
"""

import importlib
import logging
from typing import Any, Optional

from adapters.core.protocol import UniversalAdapter, is_universal_adapter, validate_adapter

logger = logging.getLogger(__name__)


class AdapterRegistryV2:
    """
    Clean adapter registry.
    
    Stores adapter instances that implement the UniversalAdapter protocol.
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._adapters: dict[str, UniversalAdapter] = {}
    
    def register(self, adapter_key: str, adapter: UniversalAdapter) -> None:
        """
        Register an adapter instance.
        
        Args:
            adapter_key: Unique adapter identifier (e.g., 'cbe_api')
            adapter: Adapter instance implementing UniversalAdapter protocol
        
        Raises:
            ValueError: If adapter_key already registered or adapter invalid
        
        Example:
            >>> from adapters.banks.cbe_new import ADAPTER
            >>> registry.register("cbe_api", ADAPTER)
        """
        if adapter_key in self._adapters:
            raise ValueError(
                f"Adapter {adapter_key!r} already registered. "
                f"Cannot register the same adapter key twice."
            )
        
        # Validate adapter implements protocol
        if not is_universal_adapter(adapter):
            errors = validate_adapter(adapter)
            raise ValueError(
                f"Adapter {adapter_key!r} does not implement UniversalAdapter protocol:\n"
                + "\n".join(f"  - {err}" for err in errors)
            )
        
        self._adapters[adapter_key] = adapter
        logger.info(f"Registered adapter: {adapter_key}")
    
    def get(self, adapter_key: str) -> UniversalAdapter:
        """
        Get adapter by key.
        
        Args:
            adapter_key: Adapter identifier
        
        Returns:
            Adapter instance implementing UniversalAdapter protocol
        
        Raises:
            KeyError: If adapter not registered
        
        Example:
            >>> adapter = registry.get("cbe_api")
            >>> outcome = adapter.parse(raw_content, ctx)
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
        List all registered adapter keys.
        
        Returns:
            Sorted list of adapter keys
        """
        return sorted(self._adapters.keys())
    
    def is_registered(self, adapter_key: str) -> bool:
        """
        Check if adapter is registered.
        
        Args:
            adapter_key: Adapter identifier
        
        Returns:
            True if registered, False otherwise
        """
        return adapter_key in self._adapters
    
    def get_stats(self) -> dict:
        """
        Get registry statistics.
        
        Returns:
            Dict with counts of total adapters (all clean)
        """
        total = len(self._adapters)
        
        return {
            'total': total,
            'clean': total,
            'migration_progress': f"{total}/{total}",
        }
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        stats = self.get_stats()
        return f"AdapterRegistryV2(total={stats['total']}, clean={stats['clean']})"


def create_registry_with_all_adapters() -> AdapterRegistryV2:
    """
    Create registry with all clean adapters.
    
    Returns:
        Fully populated AdapterRegistryV2 with all 32 clean adapters
    
    Example:
        >>> registry = create_registry_with_all_adapters()
        >>> adapter = registry.get("cbe_api")
    """
    registry = AdapterRegistryV2()
    
    # Register ALL clean adapters from adapters/banks/
    logger.info("Registering clean adapters from adapters/banks/...")
    
    # List of all clean adapters (32 total - 100% CLEAN!)
    clean_adapters = [
        ("abay_html", "adapters.banks.abay_new"),
        ("addis_fortune", "adapters.banks.addis_fortune_new"),
        ("adib_api", "adapters.banks.adib_new"),
        ("ahadu_html", "adapters.banks.ahadu_new"),
        ("amhara_html", "adapters.banks.amhara_new"),
        ("anbesa_browser", "adapters.banks.anbesa_new"),
        ("awash_ajax", "adapters.banks.awash_new"),
        ("berhan_html", "adapters.banks.berhan_new"),
        ("boa_html", "adapters.banks.boa_new"),
        ("bunna_html", "adapters.banks.bunna_new"),
        ("cbe_api", "adapters.banks.cbe_new"),
        ("cbo_html", "adapters.banks.cbo_new"),
        ("dashen_html", "adapters.banks.dashen_new"),
        ("dbe_html", "adapters.banks.dbe_new"),
        ("enat_html", "adapters.banks.enat_new"),
        ("gadaa_api", "adapters.banks.gadaa_new"),
        ("global_html", "adapters.banks.global_new"),
        ("goh_betoch_html", "adapters.banks.goh_betoch_new"),
        ("hibret_html", "adapters.banks.hibret_new"),
        ("nib_html", "adapters.banks.nib_new"),
        ("omo_html", "adapters.banks.omo_new"),
        ("oromia_html", "adapters.banks.oromia_new"),
        ("rammis_api", "adapters.banks.rammis_new"),
        ("shabelle_html", "adapters.banks.shabelle_new"),
        ("sidama_html", "adapters.banks.sidama_new"),
        ("siinqee_html", "adapters.banks.siinqee_new"),
        ("siket_html", "adapters.banks.siket_new"),
        ("tsehay_html", "adapters.banks.tsehay_new"),
        ("tsedey_html", "adapters.banks.tsedey_new"),
        ("wegagen_api", "adapters.banks.wegagen_new"),
        ("zamzam_html", "adapters.banks.zamzam_new"),
        ("zemen_ajax", "adapters.banks.zemen_new"),
    ]
    
    clean_registered = 0
    
    for adapter_key, module_path in clean_adapters:
        try:
            module = importlib.import_module(module_path)
            adapter = getattr(module, 'ADAPTER')
            registry.register(adapter_key, adapter)
            logger.info(f"✓ Registered clean adapter: {adapter_key}")
            clean_registered += 1
        except Exception as e:
            logger.warning(f"✗ Failed to register {adapter_key}: {e}")
    
    logger.info(f"Registered {clean_registered}/32 clean adapters")
    logger.info(f"Registry initialized: {clean_registered} total clean adapters")
    
    return registry


default_registry = create_registry_with_all_adapters()
