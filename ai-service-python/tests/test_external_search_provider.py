import unittest

from services.external_search_provider import (
    DisabledExternalSearchProvider,
    ExternalSearchConfigurationError,
    create_external_search_provider,
)


class _EnabledProvider:
    name = "crossref"
    enabled = True
    supports_web_search = False
    supports_page_fetch = False

    def search(self, query, limit=5):
        return [{"query": query, "limit": limit, "provider": self.name, "title": f"Result for {query}", "doi": f"10.1000/test-{hash(query) % 100000}"}]

    def status(self):
        return {"enabled": True, "status": "ready", "provider": self.name}


class ExternalSearchProviderTests(unittest.TestCase):
    def test_disabled_provider_is_read_only_and_returns_no_results(self):
        provider = DisabledExternalSearchProvider()

        self.assertEqual(provider.name, "disabled")
        self.assertFalse(provider.enabled)
        self.assertEqual(provider.search("attention prerequisites", limit=3), [])
        self.assertEqual(provider.status(), {
            "enabled": False,
            "status": "disabled",
            "message": "External academic retrieval is not enabled.",
        })

    def test_unset_and_false_values_never_call_builder(self):
        for value in (None, "", "0", "false", "no", "off", "unexpected"):
            with self.subTest(value=value):
                calls = []

                def builder(_config):
                    calls.append(True)
                    return _EnabledProvider()

                environ = {"PIXIU_EXTERNAL_SEARCH_PROVIDER": "crossref"}
                if value is not None:
                    environ["PIXIU_EXTERNAL_SEARCH_ENABLED"] = value

                provider = create_external_search_provider(
                    environ=environ,
                    builders={"crossref": builder},
                )

                self.assertIsInstance(provider, DisabledExternalSearchProvider)
                self.assertEqual(calls, [])

    def test_true_values_create_selected_provider_with_immutable_config(self):
        for value in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(value=value):
                received = []

                def builder(config):
                    with self.assertRaises(TypeError):
                        config["MUTATION"] = "denied"
                    received.append(config["PIXIU_EXTERNAL_SEARCH_PROVIDER"])
                    return _EnabledProvider()

                provider = create_external_search_provider(
                    environ={
                        "PIXIU_EXTERNAL_SEARCH_ENABLED": value,
                        "PIXIU_EXTERNAL_SEARCH_PROVIDER": "crossref",
                    },
                    builders={"crossref": builder},
                )

                self.assertTrue(provider.enabled)
                self.assertEqual(provider.name, "crossref")
                self.assertEqual(received, ["crossref"])

    def test_enabled_factory_requires_known_provider(self):
        with self.assertRaisesRegex(ExternalSearchConfigurationError, "required"):
            create_external_search_provider(
                environ={"PIXIU_EXTERNAL_SEARCH_ENABLED": "true"},
            )

        secret_value = "secret-provider-value"
        with self.assertRaises(ExternalSearchConfigurationError) as context:
            create_external_search_provider(
                environ={
                    "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                    "PIXIU_EXTERNAL_SEARCH_PROVIDER": secret_value,
                },
            )
        self.assertNotIn(secret_value, str(context.exception))
        self.assertIn("crossref", str(context.exception))
        self.assertIn("semantic_scholar", str(context.exception))

    def test_known_provider_without_client_fails_strictly(self):
        # Use a custom builder registry where only "crossref" exists to simulate
        # a provider that is in SUPPORTED_PROVIDERS but has no registered builder.
        with self.assertRaisesRegex(ExternalSearchConfigurationError, "not implemented"):
            create_external_search_provider(
                environ={
                    "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                    "PIXIU_EXTERNAL_SEARCH_PROVIDER": "arxiv",
                },
                builders={"crossref": lambda c: _EnabledProvider()},
            )

    def test_default_registry_creates_all_providers(self):
        # Academic providers (no API key needed)
        for provider_name in ("crossref", "arxiv", "semantic_scholar"):
            with self.subTest(provider=provider_name):
                provider = create_external_search_provider(
                    environ={
                        "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                        "PIXIU_EXTERNAL_SEARCH_PROVIDER": provider_name,
                    },
                )
                self.assertEqual(provider.name, provider_name)
                self.assertTrue(provider.enabled)
        # Brave and Tavily require API key
        for provider_name, env_key in (("brave", "BRAVE_SEARCH_API_KEY"), ("tavily", "TAVILY_API_KEY")):
            with self.subTest(provider=provider_name):
                environ = {
                    "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                    "PIXIU_EXTERNAL_SEARCH_PROVIDER": provider_name,
                    env_key: f"test-{provider_name}-key",
                }
                provider = create_external_search_provider(environ=environ)
                self.assertEqual(provider.name, provider_name)
                self.assertTrue(provider.enabled)

    def test_builder_failure_is_wrapped_without_leaking_error_text(self):
        def failing_builder(_config):
            raise RuntimeError("secret-token")

        with self.assertRaises(ExternalSearchConfigurationError) as context:
            create_external_search_provider(
                environ={
                    "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                    "PIXIU_EXTERNAL_SEARCH_PROVIDER": "crossref",
                },
                builders={"crossref": failing_builder},
            )

        self.assertNotIn("secret-token", str(context.exception))
        self.assertIn("could not be created", str(context.exception))
        self.assertIsNone(context.exception.__cause__)

    def test_semantic_scholar_with_api_key_environ(self):
        provider = create_external_search_provider(
            environ={
                "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                "PIXIU_EXTERNAL_SEARCH_PROVIDER": "semantic_scholar",
                "SEMANTIC_SCHOLAR_API_KEY": "test-key-from-environ",
            },
        )
        self.assertEqual(provider.name, "semantic_scholar")
        self.assertTrue(provider.enabled)
        self.assertFalse(provider.supports_web_search)
        self.assertFalse(provider.supports_page_fetch)

    def test_builder_must_return_enabled_provider_contract(self):
        invalid_values = [object(), DisabledExternalSearchProvider()]

        for value in invalid_values:
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ExternalSearchConfigurationError):
                    create_external_search_provider(
                        environ={
                            "PIXIU_EXTERNAL_SEARCH_ENABLED": "true",
                            "PIXIU_EXTERNAL_SEARCH_PROVIDER": "crossref",
                        },
                        builders={"crossref": lambda _config, result=value: result},
                    )


if __name__ == "__main__":
    unittest.main()
