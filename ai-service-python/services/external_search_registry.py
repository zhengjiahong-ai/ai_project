import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Set

from services.external_evidence import deduplicate_external_evidence


class ExternalSearchProviderRegistry:
    """Registry that manages multiple ExternalSearchProvider instances.

    Implements the same protocol interface so existing callers that use
    ``provider.search(query, limit)`` continue to work — the registry
    delegates to all enabled providers, merges results, and deduplicates.
    """

    name = "multi"
    enabled = True

    def __init__(
        self,
        providers: Dict[str, Any],
        *,
        max_workers: int = 4,
        dedup_key_fn: Optional[Callable[[Dict[str, Any]], str]] = None,
    ):
        if not isinstance(providers, dict) or not providers:
            raise ValueError("providers must be a non-empty dict mapping name -> provider instance.")
        self._providers: Dict[str, Any] = dict(providers)
        self._max_workers = max(1, int(max_workers))
        self._dedup_key_fn = dedup_key_fn or _default_dedup_key
        self._provider_names: Set[str] = set(self._providers)

        any_enabled = any(
            getattr(p, "enabled", False) is True for p in self._providers.values()
        )
        self.enabled = any_enabled

    @property
    def supports_web_search(self) -> bool:
        return any(
            getattr(p, "supports_web_search", False) is True
            for p in self._providers.values()
        )

    @property
    def supports_page_fetch(self) -> bool:
        return any(
            getattr(p, "supports_page_fetch", False) is True
            for p in self._providers.values()
        )

    @property
    def provider_names(self) -> List[str]:
        return sorted(self._provider_names)

    def get_provider(self, name: str) -> Optional[Any]:
        return self._providers.get(name.strip().lower())

    def list_providers(self) -> List[Dict[str, Any]]:
        return sorted(
            [
                {
                    "name": str(getattr(p, "name", name)),
                    "enabled": bool(getattr(p, "enabled", False)),
                    "supportsWebSearch": bool(getattr(p, "supports_web_search", False)),
                    "supportsPageFetch": bool(getattr(p, "supports_page_fetch", False)),
                    "status": _safe_status(p),
                }
                for name, p in self._providers.items()
            ],
            key=lambda item: item["name"],
        )

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search across all enabled providers, merge and deduplicate results."""
        enabled = {
            name: p
            for name, p in self._providers.items()
            if getattr(p, "enabled", False) is True
        }
        if not enabled:
            return []

        all_raw: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(enabled))) as executor:
            future_to_name = {
                executor.submit(_safe_search, p, query, limit): name
                for name, p in enabled.items()
            }
            for future in as_completed(future_to_name):
                try:
                    result = future.result()
                    if result:
                        all_raw.extend(result)
                except Exception:
                    pass

        return deduplicate_external_evidence(all_raw, limit=limit)

    def search_all(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Search across all providers, returning per-provider results and merged list."""
        enabled = {
            name: p
            for name, p in self._providers.items()
            if getattr(p, "enabled", False) is True
        }
        per_provider: Dict[str, Dict[str, Any]] = {}
        all_raw: List[Dict[str, Any]] = []

        if not enabled:
            return {
                "status": "all_disabled",
                "merged": [],
                "providers": {},
            }

        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(enabled))) as executor:
            future_to_name = {
                executor.submit(_safe_search, p, query, limit): name
                for name, p in enabled.items()
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    items = future.result()
                except Exception:
                    items = None
                if items is None:
                    per_provider[name] = {"status": "failed", "items": []}
                else:
                    per_provider[name] = {"status": "success", "items": list(items)}
                    all_raw.extend(items)

        merged = deduplicate_external_evidence(all_raw, limit=limit)
        return {
            "status": "success",
            "merged": merged,
            "providers": per_provider,
        }

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "status": "ready" if self.enabled else "all_disabled",
            "provider": "multi",
            "providers": self.list_providers(),
        }


def _safe_search(provider: Any, query: str, limit: int) -> Optional[List[Dict[str, Any]]]:
    """Call provider.search, returning None on any failure."""
    try:
        result = provider.search(query, limit)
        return list(result) if isinstance(result, list) else None
    except Exception:
        return None


def _safe_status(provider: Any) -> Dict[str, Any]:
    try:
        status = provider.status()
        return copy.deepcopy(status) if isinstance(status, dict) else {}
    except Exception:
        return {}


def _default_dedup_key(item: Dict[str, Any]) -> str:
    doi = str(item.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    provider_id = str(item.get("providerId") or "").strip().lower()
    provider = str(item.get("provider") or "").strip().lower()
    if provider_id and provider:
        return f"pid:{provider}:{provider_id}"
    title = " ".join(str(item.get("title") or "").strip().lower().split())
    if title:
        return f"title:{title}"
    return ""
