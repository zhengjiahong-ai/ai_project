import os
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, runtime_checkable


EXTERNAL_SEARCH_ENABLED_ENV = "PIXIU_EXTERNAL_SEARCH_ENABLED"
EXTERNAL_SEARCH_PROVIDER_ENV = "PIXIU_EXTERNAL_SEARCH_PROVIDER"
EXTERNAL_SEARCH_PROVIDERS_ENV = "PIXIU_EXTERNAL_SEARCH_PROVIDERS"
ENABLED_VALUES = {"1", "true", "yes", "on"}
SUPPORTED_PROVIDERS = {"crossref", "semantic_scholar", "arxiv", "brave", "tavily"}


class ExternalSearchConfigurationError(ValueError):
    pass


@runtime_checkable
class ExternalSearchProvider(Protocol):
    name: str
    enabled: bool
    supports_web_search: bool
    supports_page_fetch: bool

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        ...

    def status(self) -> Dict[str, Any]:
        ...


class DisabledExternalSearchProvider:
    name = "disabled"
    enabled = False
    supports_web_search = False
    supports_page_fetch = False

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


def _build_arxiv_provider(config: Mapping[str, str]) -> ExternalSearchProvider:
    from services.providers.arxiv_provider import build_arxiv_provider

    return build_arxiv_provider(config)


def _build_semantic_scholar_provider(config: Mapping[str, str]) -> ExternalSearchProvider:
    from services.providers.semantic_scholar_provider import build_semantic_scholar_provider

    return build_semantic_scholar_provider(config)


def _build_brave_search_provider(config: Mapping[str, str]) -> ExternalSearchProvider:
    from services.providers.brave_search_provider import build_brave_search_provider

    return build_brave_search_provider(config)


def _build_tavily_search_provider(config: Mapping[str, str]) -> ExternalSearchProvider:
    from services.providers.tavily_provider import build_tavily_provider

    return build_tavily_provider(config)


def create_external_search_provider(
    environ: Optional[Mapping[str, str]] = None,
    builders: Optional[Mapping[str, ProviderBuilder]] = None,
) -> ExternalSearchProvider:
    source = os.environ if environ is None else environ
    enabled = str(source.get(EXTERNAL_SEARCH_ENABLED_ENV, "")).strip().lower() in ENABLED_VALUES
    if not enabled:
        return DisabledExternalSearchProvider()

    providers_env = str(source.get(EXTERNAL_SEARCH_PROVIDERS_ENV, "")).strip()
    if providers_env:
        providers_env = _auto_enable_semantic_scholar(providers_env, source)
        return _create_multi_provider(providers_env, source, builders)

    provider_name = str(source.get(EXTERNAL_SEARCH_PROVIDER_ENV, "")).strip().lower()
    if not provider_name:
        raise ExternalSearchConfigurationError(
            "PIXIU_EXTERNAL_SEARCH_PROVIDER is required when external search is enabled "
            "(or set PIXIU_EXTERNAL_SEARCH_PROVIDERS for multi-provider mode)."
        )
    if provider_name not in SUPPORTED_PROVIDERS:
        raise ExternalSearchConfigurationError(
            "PIXIU_EXTERNAL_SEARCH_PROVIDER must be one of: crossref, semantic_scholar, arxiv, brave, tavily."
        )

    registry = {"crossref": _build_crossref_provider, "arxiv": _build_arxiv_provider, "semantic_scholar": _build_semantic_scholar_provider, "brave": _build_brave_search_provider, "tavily": _build_tavily_search_provider} if builders is None else builders
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


def _semantic_scholar_api_key_available(source: Mapping[str, str]) -> bool:
    """Check whether a Semantic Scholar API key is configured via env or settings."""
    env_key = str(source.get("SEMANTIC_SCHOLAR_API_KEY", "")).strip()
    if env_key:
        return True
    try:
        from core.config import settings

        return bool(settings.semantic_scholar_api_key.strip())
    except Exception:
        return False


def _auto_enable_semantic_scholar(
    providers_env: str,
    source: Mapping[str, str],
) -> str:
    """Append semantic_scholar to the provider list when an API key is configured."""
    requested = [
        name.strip().lower()
        for name in providers_env.split(",")
        if name.strip()
    ]
    if "semantic_scholar" in requested:
        return providers_env
    if _semantic_scholar_api_key_available(source):
        return providers_env + ",semantic_scholar"
    return providers_env


def _create_multi_provider(
    providers_env: str,
    source: Mapping[str, str],
    builders: Optional[Mapping[str, ProviderBuilder]] = None,
) -> ExternalSearchProvider:
    from services.external_search_registry import ExternalSearchProviderRegistry

    requested = [
        name.strip().lower()
        for name in providers_env.split(",")
        if name.strip()
    ]
    if not requested:
        return DisabledExternalSearchProvider()

    seen = set()
    unique_names = []
    for name in requested:
        if name not in seen:
            seen.add(name)
            unique_names.append(name)

    unknown = [name for name in unique_names if name not in SUPPORTED_PROVIDERS]
    if unknown:
        raise ExternalSearchConfigurationError(
            f"PIXIU_EXTERNAL_SEARCH_PROVIDERS contains unknown provider(s): {', '.join(sorted(unknown))}. "
            f"Supported: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
        )

    registry = {"crossref": _build_crossref_provider, "arxiv": _build_arxiv_provider, "semantic_scholar": _build_semantic_scholar_provider, "brave": _build_brave_search_provider, "tavily": _build_tavily_search_provider} if builders is None else builders
    unimplemented = [name for name in unique_names if name not in registry]
    if unimplemented:
        raise ExternalSearchConfigurationError(
            f"External search provider client(s) not implemented: {', '.join(sorted(unimplemented))}."
        )

    config = MappingProxyType(dict(source))
    instances: Dict[str, ExternalSearchProvider] = {}
    for name in unique_names:
        try:
            provider = registry[name](config)
        except Exception:
            raise ExternalSearchConfigurationError(
                f"External search provider '{name}' could not be created."
            ) from None
        if (
            not isinstance(provider, ExternalSearchProvider)
            or provider.enabled is not True
            or str(provider.name).strip().lower() != name
        ):
            raise ExternalSearchConfigurationError(
                f"External search provider builder for '{name}' returned an invalid provider."
            )
        instances[name] = provider

    return ExternalSearchProviderRegistry(instances)
