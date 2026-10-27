from typing import Any

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

    def __init__(self):
        self._adapters: dict[str, Any] = {}

    def register(self, adapter_key: str, adapter_module: Any) -> None:
        if adapter_key in self._adapters:
            raise ValueError(
                f"Adapter {adapter_key!r} already registered. "
                f"Cannot register the same adapter key twice."
            )
        self._adapters[adapter_key] = adapter_module

    def get(self, adapter_key: str) -> Any:
        if adapter_key not in self._adapters:
            available = ', '.join(sorted(self._adapters.keys()))
            raise KeyError(
                f"Adapter {adapter_key!r} not registered. "
                f"Available adapters: {available}"
            )
        return self._adapters[adapter_key]

    def list_keys(self) -> list[str]:
        return sorted(self._adapters.keys())

    def is_registered(self, adapter_key: str) -> bool:
        return adapter_key in self._adapters

default_registry = AdapterRegistry()

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
