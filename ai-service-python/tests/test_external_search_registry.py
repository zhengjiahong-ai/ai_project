import unittest
from unittest.mock import patch

from services.external_search_provider import (
    DisabledExternalSearchProvider,
    ExternalSearchConfigurationError,
    create_external_search_provider,
)
from services.external_search_registry import ExternalSearchProviderRegistry


class _EnabledProvider:
    _counter = 0

    def __init__(self, name="crossref", web=False, fetch=False):
        _EnabledProvider._counter += 1
        self._id = _EnabledProvider._counter
        self.name = name
        self.enabled = True
        self.supports_web_search = web
        self.supports_page_fetch = fetch

    def search(self, query, limit=5):
        return [{
            "provider": self.name,
            "providerId": f"{self.name}-id-{self._id}",
            "title": f"Sample Result from {self.name} for {query}",
            "doi": f"10.1000/{self.name}.{self._id}",
            "query": query,
            "limit": limit,
        }]

    def status(self):
        return {"enabled": True, "status": "ready", "provider": self.name}


class _DisabledProvider:
    name = "crossref"
    enabled = False
    supports_web_search = False
    supports_page_fetch = False

    def search(self, query, limit=5):
        return []

    def status(self):
        return {"enabled": False, "status": "disabled"}


class _FailingProvider:
    name = "crossref"
    enabled = True
    supports_web_search = False
    supports_page_fetch = False

    def search(self, query, limit=5):
        raise RuntimeError("provider-down")

    def status(self):
        return {"enabled": True, "status": "error"}


class ExternalSearchRegistryTests(unittest.TestCase):
    def test_registry_name_and_enabled(self):
        reg = ExternalSearchProviderRegistry(
            {"crossref": _EnabledProvider("crossref"), "arxiv": _EnabledProvider("arxiv")}
        )
        self.assertEqual(reg.name, "multi")
        self.assertTrue(reg.enabled)
        self.assertFalse(reg.supports_web_search)
        self.assertFalse(reg.supports_page_fetch)

    def test_registry_disabled_when_all_providers_disabled(self):
        reg = ExternalSearchProviderRegistry({"a": _DisabledProvider()})
        self.assertFalse(reg.enabled)

    def test_registry_capability_flags_reflect_sub_providers(self):
        web_provider = _EnabledProvider("web", web=True)
        fetch_provider = _EnabledProvider("fetch", fetch=True)
        reg = ExternalSearchProviderRegistry({"web": web_provider, "fetch": fetch_provider})
        self.assertTrue(reg.supports_web_search)
        self.assertTrue(reg.supports_page_fetch)

    def test_search_merges_and_deduplicates_across_providers(self):
        reg = ExternalSearchProviderRegistry(
            {
                "a": _EnabledProvider("a"),
                "b": _EnabledProvider("b"),
            }
        )
        results = reg.search("test query", limit=10)
        self.assertEqual(len(results), 2)
        names = sorted(r["provider"] for r in results)
        self.assertEqual(names, ["a", "b"])

    def test_search_all_returns_per_provider_breakdown(self):
        reg = ExternalSearchProviderRegistry(
            {"a": _EnabledProvider("a"), "b": _EnabledProvider("b")}
        )
        result = reg.search_all("test", limit=5)
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["merged"]), 2)
        self.assertIn("a", result["providers"])
        self.assertIn("b", result["providers"])
        self.assertEqual(result["providers"]["a"]["status"], "success")

    def test_search_all_with_disabled_providers_skips_them(self):
        reg = ExternalSearchProviderRegistry(
            {"enabled": _EnabledProvider("enabled"), "disabled": _DisabledProvider()}
        )
        result = reg.search_all("test", limit=5)
        self.assertEqual(len(result["merged"]), 1)
        self.assertNotIn("disabled", result["providers"])

    def test_search_all_when_all_disabled(self):
        reg = ExternalSearchProviderRegistry({"a": _DisabledProvider(), "b": _DisabledProvider()})
        result = reg.search_all("test", limit=5)
        self.assertEqual(result["status"], "all_disabled")
        self.assertEqual(result["merged"], [])
        self.assertEqual(result["providers"], {})

    def test_search_survives_provider_failure(self):
        reg = ExternalSearchProviderRegistry(
            {"good": _EnabledProvider("good"), "bad": _FailingProvider()}
        )
        results = reg.search("test", limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["provider"], "good")

    def test_search_all_survives_provider_failure(self):
        reg = ExternalSearchProviderRegistry(
            {"good": _EnabledProvider("good"), "bad": _FailingProvider()}
        )
        result = reg.search_all("test", limit=5)
        self.assertEqual(result["providers"]["good"]["status"], "success")
        self.assertEqual(result["providers"]["bad"]["status"], "failed")

    def test_list_providers(self):
        reg = ExternalSearchProviderRegistry(
            {"crossref": _EnabledProvider("crossref"), "arxiv": _EnabledProvider("arxiv", web=False)}
        )
        providers = reg.list_providers()
        self.assertEqual(len(providers), 2)
        names = [p["name"] for p in providers]
        self.assertEqual(names, ["arxiv", "crossref"])

    def test_list_providers_includes_capabilities(self):
        reg = ExternalSearchProviderRegistry({"a": _EnabledProvider("a", web=True)})
        info = reg.list_providers()[0]
        self.assertTrue(info["supportsWebSearch"])
        self.assertFalse(info["supportsPageFetch"])

    def test_get_provider(self):
        a = _EnabledProvider("crossref")
        reg = ExternalSearchProviderRegistry({"crossref": a})
        self.assertIs(reg.get_provider("crossref"), a)
        self.assertIsNone(reg.get_provider("unknown"))

    def test_provider_names(self):
        reg = ExternalSearchProviderRegistry({"b": _EnabledProvider("b"), "a": _EnabledProvider("a")})
        self.assertEqual(reg.provider_names, ["a", "b"])

    def test_status(self):
        reg = ExternalSearchProviderRegistry({"crossref": _EnabledProvider("crossref")})
        status = reg.status()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["provider"], "multi")
        self.assertIn("providers", status)

    def test_all_disabled_status(self):
        reg = ExternalSearchProviderRegistry({"a": _DisabledProvider()})
        status = reg.status()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["status"], "all_disabled")

    def test_empty_providers_dict_rejected(self):
        with self.assertRaises(ValueError):
            ExternalSearchProviderRegistry({})

    def test_registry_search_with_no_enabled_providers_returns_empty(self):
        reg = ExternalSearchProviderRegistry({"a": _DisabledProvider()})
        self.assertEqual(reg.search("test"), [])

    def test_constructor_enforces_dict_type(self):
        with self.assertRaises(ValueError):
            ExternalSearchProviderRegistry([])
        with self.assertRaises(ValueError):
            ExternalSearchProviderRegistry(None)


class ExternalSearchMultiProviderFactoryTests(unittest.TestCase):
    def test_multi_provider_creates_registry(self):
        provider = create_external_search_provider(
            environ={
                "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                "PIXIU_EXTERNAL_SEARCH_PROVIDERS": "crossref",
            },
        )
        self.assertIsInstance(provider, ExternalSearchProviderRegistry)
        self.assertEqual(provider.name, "multi")
        self.assertTrue(provider.enabled)

    def test_multi_provider_with_multiple_names(self):
        provider = create_external_search_provider(
            environ={
                "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                "PIXIU_EXTERNAL_SEARCH_PROVIDERS": "crossref ,  crossref  ",
            },
        )
        self.assertIsInstance(provider, ExternalSearchProviderRegistry)
        self.assertEqual(len(provider._providers), 1)

    def test_multi_provider_unknown_name_fails(self):
        with self.assertRaisesRegex(ExternalSearchConfigurationError, "unknown provider"):
            create_external_search_provider(
                environ={
                    "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                    "PIXIU_EXTERNAL_SEARCH_PROVIDERS": "unknown_provider",
                },
            )

    def test_multi_provider_unimplemented_fails(self):
        with self.assertRaisesRegex(ExternalSearchConfigurationError, "not implemented"):
            create_external_search_provider(
                environ={
                    "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                    "PIXIU_EXTERNAL_SEARCH_PROVIDERS": "semantic_scholar",
                },
            )

    def test_multi_provider_empty_list_returns_disabled(self):
        provider = create_external_search_provider(
            environ={
                "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                "PIXIU_EXTERNAL_SEARCH_PROVIDERS": "  ,  ,  ",
            },
        )
        self.assertIsInstance(provider, DisabledExternalSearchProvider)

    def test_multi_provider_takes_precedence_over_single(self):
        provider = create_external_search_provider(
            environ={
                "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                "PIXIU_EXTERNAL_SEARCH_PROVIDER": "semantic_scholar",
                "PIXIU_EXTERNAL_SEARCH_PROVIDERS": "crossref",
            },
        )
        self.assertIsInstance(provider, ExternalSearchProviderRegistry)

    def test_disabled_when_enabled_flag_is_false(self):
        for value in ("0", "false", "no", "off", ""):
            with self.subTest(value=value):
                provider = create_external_search_provider(
                    environ={
                        "PIXIU_EXTERNAL_SEARCH_ENABLED": value,
                        "PIXIU_EXTERNAL_SEARCH_PROVIDERS": "crossref",
                    },
                )
                self.assertIsInstance(provider, DisabledExternalSearchProvider)

    def test_backward_compatible_single_provider_still_works(self):
        provider = create_external_search_provider(
            environ={
                "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                "PIXIU_EXTERNAL_SEARCH_PROVIDER": "crossref",
            },
        )
        self.assertEqual(provider.name, "crossref")
        self.assertTrue(provider.enabled)
        self.assertFalse(provider.supports_web_search)
        self.assertFalse(provider.supports_page_fetch)

    def test_multi_provider_with_custom_builders(self):
        def build_a(config):
            return _EnabledProvider("test_a")

        def build_b(config):
            return _EnabledProvider("test_b", web=True)

        from services.external_search_provider import SUPPORTED_PROVIDERS
        old = set(SUPPORTED_PROVIDERS)
        SUPPORTED_PROVIDERS.update({"test_a", "test_b"})
        try:
            provider = create_external_search_provider(
                environ={
                    "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                    "PIXIU_EXTERNAL_SEARCH_PROVIDERS": "test_a,test_b",
                },
                builders={"test_a": build_a, "test_b": build_b},
            )
            self.assertIsInstance(provider, ExternalSearchProviderRegistry)
            self.assertTrue(provider.supports_web_search)
            self.assertFalse(provider.supports_page_fetch)
        finally:
            SUPPORTED_PROVIDERS.clear()
            SUPPORTED_PROVIDERS.update(old)


class ProtocolAttributesTests(unittest.TestCase):
    def test_disabled_provider_has_capability_flags(self):
        p = DisabledExternalSearchProvider()
        self.assertFalse(p.supports_web_search)
        self.assertFalse(p.supports_page_fetch)

    def test_crossref_provider_has_capability_flags(self):
        from services.providers.crossref import CrossrefProvider
        p = CrossrefProvider()
        self.assertFalse(p.supports_web_search)
        self.assertFalse(p.supports_page_fetch)


if __name__ == "__main__":
    unittest.main()
