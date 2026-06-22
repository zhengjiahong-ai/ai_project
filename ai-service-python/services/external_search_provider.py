import os
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, runtime_checkable


EXTERNAL_SEARCH_ENABLED_ENV = "PIXIU_EXTERNAL_SEARCH_ENABLED"
EXTERNAL_SEARCH_PROVIDER_ENV = "PIXIU_EXTERNAL_SEARCH_PROVIDER"
ENABLED_VALUES = {"1", "true", "yes", "on"}
SUPPORTED_PROVIDERS = {"crossref", "semantic_scholar"}


class ExternalSearchConfigurationError(ValueError):
    pass


@runtime_checkable
class ExternalSearchProvider(Protocol):
    name: str
    enabled: bool

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        ...

    def status(self) -> Dict[str, Any]:
        ...


class DisabledExternalSearchProvider:
    name = "disabled"
    enabled = False

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return []

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "status": "disabled",
            "message": "External academic retrieval is not enabled.",
        }


ProviderBuilder = Callable[[Mapping[str, str]], ExternalSearchProvider]


def _build_crossref_provider(config: Mapping[str, str]) -> ExternalSearchProvider:
    from services.providers.crossref import build_crossref_provider

    return build_crossref_provider(config)


def create_external_search_provider(
    environ: Optional[Mapping[str, str]] = None,
    builders: Optional[Mapping[str, ProviderBuilder]] = None,
) -> ExternalSearchProvider:
    source = os.environ if environ is None else environ
    enabled = str(source.get(EXTERNAL_SEARCH_ENABLED_ENV, "")).strip().lower() in ENABLED_VALUES
    if not enabled:
        return DisabledExternalSearchProvider()

    provider_name = str(source.get(EXTERNAL_SEARCH_PROVIDER_ENV, "")).strip().lower()
    if not provider_name:
        raise ExternalSearchConfigurationError(
            "PIXIU_EXTERNAL_SEARCH_PROVIDER is required when external search is enabled."
        )
    if provider_name not in SUPPORTED_PROVIDERS:
        raise ExternalSearchConfigurationError(
            "PIXIU_EXTERNAL_SEARCH_PROVIDER must be one of: crossref, semantic_scholar."
        )

    registry = {"crossref": _build_crossref_provider} if builders is None else builders
    builder = registry.get(provider_name)
    if builder is None:
        raise ExternalSearchConfigurationError(
            "External search provider client is not implemented for the selected provider."
        )

    config = MappingProxyType(dict(source))
    try:
        provider = builder(config)
    except Exception:
        raise ExternalSearchConfigurationError(
            "External search provider client could not be created."
        ) from None

    if (
        not isinstance(provider, ExternalSearchProvider)
        or provider.enabled is not True
        or str(provider.name).strip().lower() != provider_name
    ):
        raise ExternalSearchConfigurationError(
            "External search provider builder returned an invalid provider."
        )
    return provider
