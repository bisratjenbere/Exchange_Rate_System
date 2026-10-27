import pytest
from infrastructure.adapter_registry import AdapterRegistry, default_registry

class MockAdapter:
    def parse(self, content):
        return []

    def schema_fingerprint(self, content):
        return "mock_fingerprint"

class TestAdapterRegistryBasics:

    def test_register_and_get(self):
        registry = AdapterRegistry()
        mock_adapter = MockAdapter()

        registry.register("test_adapter", mock_adapter)
        retrieved = registry.get("test_adapter")

        assert retrieved is mock_adapter

    def test_register_multiple_adapters(self):
        registry = AdapterRegistry()
        mock1 = MockAdapter()
        mock2 = MockAdapter()
        mock3 = MockAdapter()

        registry.register("adapter1", mock1)
        registry.register("adapter2", mock2)
        registry.register("adapter3", mock3)

        assert registry.get("adapter1") is mock1
        assert registry.get("adapter2") is mock2
        assert registry.get("adapter3") is mock3

    def test_get_unregistered_adapter_raises_keyerror(self):
        registry = AdapterRegistry()
        registry.register("adapter1", MockAdapter())

        with pytest.raises(KeyError) as exc_info:
            registry.get("nonexistent")

        error_msg = str(exc_info.value)
        assert "nonexistent" in error_msg
        assert "not registered" in error_msg
        assert "Available adapters" in error_msg

class TestAdapterRegistryDuplicates:

    def test_duplicate_registration_raises_valueerror(self):
        registry = AdapterRegistry()
        mock1 = MockAdapter()
        mock2 = MockAdapter()

        registry.register("test_adapter", mock1)

        with pytest.raises(ValueError) as exc_info:
            registry.register("test_adapter", mock2)

        error_msg = str(exc_info.value)
        assert "test_adapter" in error_msg
        assert "already registered" in error_msg

    def test_duplicate_prevents_overwrite(self):
        registry = AdapterRegistry()
        mock1 = MockAdapter()
        mock2 = MockAdapter()

        registry.register("test_adapter", mock1)

        try:
            registry.register("test_adapter", mock2)
        except ValueError:
            pass

        assert registry.get("test_adapter") is mock1

class TestAdapterRegistryKeyListing:

    def test_list_keys_empty_registry(self):
        registry = AdapterRegistry()
        assert registry.list_keys() == []

    def test_list_keys_with_adapters(self):
        registry = AdapterRegistry()

        registry.register("zebra_adapter", MockAdapter())
        registry.register("alpha_adapter", MockAdapter())
        registry.register("beta_adapter", MockAdapter())

        keys = registry.list_keys()
        assert keys == ["alpha_adapter", "beta_adapter", "zebra_adapter"]

    def test_is_registered_returns_true_for_registered(self):
        registry = AdapterRegistry()
        registry.register("test_adapter", MockAdapter())

        assert registry.is_registered("test_adapter") is True

    def test_is_registered_returns_false_for_unregistered(self):
        registry = AdapterRegistry()
        registry.register("test_adapter", MockAdapter())

        assert registry.is_registered("nonexistent") is False

    def test_is_registered_empty_registry(self):
        registry = AdapterRegistry()
        assert registry.is_registered("anything") is False

class TestDefaultRegistry:

    def test_default_registry_exists(self):
        assert default_registry is not None
        assert isinstance(default_registry, AdapterRegistry)

    def test_default_registry_has_all_adapters(self):
        keys = default_registry.list_keys()

        assert len(keys) == 31

    def test_default_registry_has_cbe(self):
        assert default_registry.is_registered("cbe_api")
        adapter = default_registry.get("cbe_api")
        assert hasattr(adapter, 'parse')

    def test_default_registry_has_dashen(self):
        assert default_registry.is_registered("dashen_html")
        adapter = default_registry.get("dashen_html")
        assert hasattr(adapter, 'parse')

    def test_default_registry_has_global(self):
        assert default_registry.is_registered("global_html")
        adapter = default_registry.get("global_html")
        assert hasattr(adapter, 'parse')

    def test_default_registry_has_awash(self):
        assert default_registry.is_registered("awash_ajax")
        adapter = default_registry.get("awash_ajax")
        assert hasattr(adapter, 'parse')

    def test_default_registry_has_wegagen(self):
        assert default_registry.is_registered("wegagen_api")
        adapter = default_registry.get("wegagen_api")
        assert hasattr(adapter, 'parse')

    def test_default_registry_all_adapters_have_parse(self):
        for adapter_key in default_registry.list_keys():
            adapter = default_registry.get(adapter_key)
            assert hasattr(adapter, 'parse'), \
                f"Adapter {adapter_key} missing parse() method"

class TestAdapterRegistryErrorMessages:

    def test_keyerror_shows_available_adapters(self):
        registry = AdapterRegistry()
        registry.register("adapter1", MockAdapter())
        registry.register("adapter2", MockAdapter())
        registry.register("adapter3", MockAdapter())

        with pytest.raises(KeyError) as exc_info:
            registry.get("nonexistent")

        error_msg = str(exc_info.value)
        assert "adapter1" in error_msg
        assert "adapter2" in error_msg
        assert "adapter3" in error_msg

    def test_keyerror_message_on_empty_registry(self):
        registry = AdapterRegistry()

        with pytest.raises(KeyError) as exc_info:
            registry.get("anything")

        error_msg = str(exc_info.value)
        assert "not registered" in error_msg
