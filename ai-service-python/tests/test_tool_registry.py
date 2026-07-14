import json
import os
import unittest
from unittest.mock import Mock, patch

from services.tool_registry import (
    ToolRegistry,
    ToolValidationError,
    get_tool_registry,
    reset_tool_registry,
)


VALID_INPUT_SCHEMA = {
    "type": "object",
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "additionalProperties": False,
}

VALID_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["text"],
                "properties": {"text": {"type": "string", "minLength": 1}},
                "additionalProperties": True,
            },
        }
    },
    "additionalProperties": True,
}

VALID_SAFETY_SCOPE = {
    "access": "read_only",
    "dataScopes": ["internal_library"],
    "networkAccess": False,
    "sideEffects": False,
    "sensitiveOutput": True,
}


def _external_evidence(provider_id, year):
    return {
        "provider": "Crossref",
        "providerId": provider_id,
        "title": f"Paper {provider_id}",
        "authors": ["Ada Lovelace"],
        "year": year,
        "abstract": "Bounded abstract.",
        "doi": "",
        "url": "",
        "retrievedAt": "2026-06-22T00:00:00Z",
        "query": "retrieval systems",
        "license": "",
    }


def register_test_tool(registry, handler=None, **overrides):
    values = {
        "name": "search",
        "version": "1.0.0",
        "description": "Search the internal library.",
        "input_schema": VALID_INPUT_SCHEMA,
        "output_schema": VALID_OUTPUT_SCHEMA,
        "safety_scope": VALID_SAFETY_SCOPE,
        "handler": handler or (lambda payload: {"items": [{"text": payload["query"]}]}),
    }
    values.update(overrides)
    return registry.register(**values)


class ToolRegistryContractTests(unittest.TestCase):
    def tearDown(self):
        from services import trace_service

        trace_service.clear_traces()
        reset_tool_registry()

    def test_default_registry_exposes_nine_serializable_versioned_contracts(self):
        registry = get_tool_registry()

        contracts = registry.list_tools()

        self.assertEqual(registry.schemaVersion, "1.0")
        self.assertEqual(len(contracts), 14)
        self.assertEqual(
            set(contracts[0]),
            {"name", "version", "description", "inputSchema", "outputSchema", "safetyScope"},
        )
        self.assertTrue(all(contract["version"] == "1.0.0" for contract in contracts))
        self.assertTrue(all(contract["inputSchema"]["additionalProperties"] is False for contract in contracts))
        self.assertTrue(all(set(contract["safetyScope"]) == set(VALID_SAFETY_SCOPE) for contract in contracts))
        json.dumps(contracts)

        contracts[0]["inputSchema"]["properties"]["tampered"] = {"type": "string"}
        self.assertNotIn("tampered", registry.list_tools()[0]["inputSchema"]["properties"])

    def test_external_academic_tool_has_strict_versioned_contract(self):
        registry = get_tool_registry()
        contract = next(item for item in registry.list_tools() if item["name"] == "retrieve_external_academic")

        self.assertEqual(contract["version"], "1.0.0")
        self.assertEqual(contract["inputSchema"], {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                "yearFrom": {"type": "integer", "minimum": 1000, "maximum": 9999},
                "yearTo": {"type": "integer", "minimum": 1000, "maximum": 9999},
            },
            "additionalProperties": False,
        })
        self.assertEqual(contract["safetyScope"], {
            "access": "read_only",
            "dataScopes": ["external_academic_metadata"],
            "networkAccess": True,
            "sideEffects": False,
            "sensitiveOutput": True,
        })
        self.assertEqual(contract["outputSchema"]["required"], ["status", "provider", "items"])
        self.assertFalse(contract["outputSchema"]["additionalProperties"])
        item_schema = contract["outputSchema"]["properties"]["items"]["items"]
        self.assertEqual(
            set(item_schema["required"]),
            {
                "sourceId", "sourceType", "provider", "providerId", "title", "authors",
                "year", "abstract", "doi", "url", "retrievedAt", "query", "license",
            },
        )
        self.assertFalse(item_schema["additionalProperties"])

    def test_external_academic_tool_is_structurally_disabled_without_building_network_client(self):
        from services import external_search_provider

        with patch.dict(os.environ, {}, clear=True), patch.object(
            external_search_provider,
            "_build_crossref_provider",
            side_effect=AssertionError("network provider must not be built"),
        ):
            result = get_tool_registry().invoke(
                "retrieve_external_academic",
                {"query": "retrieval systems"},
            )

        self.assertEqual(result, {"status": "disabled", "provider": "disabled", "items": []})

    def test_external_academic_tool_reuses_provider_and_filters_years(self):
        provider = Mock(name="crossref-provider")
        provider.name = "crossref"
        provider.enabled = True
        provider.search.return_value = [
            _external_evidence("work-2020", 2020),
            _external_evidence("work-2021", 2021),
            _external_evidence("work-none", None),
            _external_evidence("work-2023", 2023),
        ]

        with patch("services.tool_registry.create_external_search_provider", return_value=provider) as factory:
            registry = get_tool_registry()
            first = registry.invoke(
                "retrieve_external_academic",
                {"query": "  retrieval   systems  ", "limit": 5, "yearFrom": 2021, "yearTo": 2022},
            )
            second = registry.invoke(
                "retrieve_external_academic",
                {"query": "retrieval systems", "limit": 2},
            )

        factory.assert_called_once_with()
        self.assertEqual(provider.search.call_args_list[0].args, ("retrieval systems", 5))
        self.assertEqual(provider.search.call_args_list[1].args, ("retrieval systems", 2))
        self.assertEqual(first["status"], "success")
        self.assertEqual(first["provider"], "crossref")
        self.assertEqual([item["year"] for item in first["items"]], [2021])
        self.assertEqual(len(second["items"]), 2)
        self.assertTrue(all(item["sourceType"] == "external_academic" for item in second["items"]))

    def test_external_academic_trace_summary_uses_query_digest_not_raw_query(self):
        from services import trace_service

        provider = Mock(name="crossref-provider")
        provider.name = "crossref"
        provider.enabled = True
        provider.search.return_value = [_external_evidence("work-2024", 2024)]
        trace_id = trace_service.start_trace("unit_external_search")

        with patch("services.tool_registry.create_external_search_provider", return_value=provider):
            get_tool_registry().invoke(
                "retrieve_external_academic",
                {"query": "retrieval systems private-marker", "limit": 1},
            )

        summary = trace_service.get_trace_summary(trace_id)["trace"]
        step = next(item for item in summary["steps"] if item["name"] == "tool_retrieve_external_academic")
        query_summary = step["meta"]["querySummary"]
        self.assertEqual(set(query_summary), {"queryHash", "queryLength", "tokenCount"})
        self.assertEqual(len(query_summary["queryHash"]), 16)
        self.assertNotIn("retrieval systems", str(step))
        self.assertNotIn("private-marker", str(step))

    def test_external_academic_tool_stops_when_task_budget_is_exhausted(self):
        from services import trace_service

        provider = Mock(name="crossref-provider")
        provider.name = "crossref"
        provider.enabled = True
        provider.search.return_value = [_external_evidence("work-2024", 2024)]

        trace_id = trace_service.start_trace("unit_external_search")
        with patch("services.tool_registry.create_external_search_provider", return_value=provider):
            registry = get_tool_registry()
            for _index in range(10):
                result = registry.invoke("retrieve_external_academic", {"query": "retrieval systems", "limit": 5})
                self.assertEqual(result["status"], "success")
            blocked = registry.invoke("retrieve_external_academic", {"query": "retrieval systems", "limit": 5})

        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(blocked["status"], "budget_exceeded")
        self.assertEqual(blocked["provider"], "crossref")
        self.assertEqual(blocked["items"], [])
        self.assertIn("call budget", blocked["reason"])
        self.assertEqual(provider.search.call_count, 10)
        self.assertEqual(snapshot["counters"]["externalSearchCalls"], 10)
        self.assertEqual(snapshot["counters"]["externalEvidenceCount"], 10)
        self.assertEqual(snapshot["counters"]["externalSearchBudgetBlocks"], 1)

    def test_external_academic_tool_returns_sanitized_failure_and_counts_it(self):
        from services import trace_service

        provider = Mock(name="crossref-provider")
        provider.name = "crossref"
        provider.enabled = True
        provider.search.side_effect = RuntimeError("sk-secret full response body with private query")

        trace_id = trace_service.start_trace("unit_external_search")
        with patch("services.tool_registry.create_external_search_provider", return_value=provider):
            result = get_tool_registry().invoke("retrieve_external_academic", {"query": "retrieval systems", "limit": 2})

        snapshot = trace_service.get_trace_snapshot(trace_id)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["provider"], "crossref")
        self.assertEqual(result["items"], [])
        self.assertNotIn("sk-secret", result["reason"])
        self.assertNotIn("full response body", result["reason"])
        self.assertEqual(snapshot["counters"]["externalSearchFailures"], 1)
        self.assertEqual(snapshot["counters"]["externalSearchCalls"], 0)

    def test_external_academic_tool_rejects_unsafe_and_out_of_bounds_inputs(self):
        registry = get_tool_registry()
        invalid_cases = [
            ({"query": "x" * 257}, "maxLength"),
            ({"query": "browse https://evil.example"}, "safe academic query"),
            ({"query": "valid query", "limit": 6}, "at most 5"),
            ({"query": "valid query", "yearFrom": 999}, "at least 1000"),
            ({"query": "valid query", "yearTo": 10000}, "at most 9999"),
            ({"query": "valid query", "yearFrom": 2025, "yearTo": 2024}, "yearFrom must not exceed yearTo"),
            ({"query": "valid query", "provider": "evil"}, "unknown field"),
        ]

        for payload, pattern in invalid_cases:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ToolValidationError, pattern):
                    registry.invoke("retrieve_external_academic", payload)

    def test_graph_neighborhood_tool_is_strict_and_read_only(self):
        registry = get_tool_registry()
        contract = next(item for item in registry.list_tools() if item["name"] == "read_knowledge_graph_neighborhood")

        self.assertEqual(contract["safetyScope"]["access"], "read_only")
        self.assertFalse(contract["safetyScope"]["networkAccess"])
        self.assertFalse(contract["safetyScope"]["sideEffects"])
        self.assertTrue(contract["safetyScope"]["sensitiveOutput"])
        with self.assertRaisesRegex(ToolValidationError, "unexpected"):
            registry.invoke("read_knowledge_graph_neighborhood", {"seedTerms": ["accuracy"], "unexpected": True})

    def test_registration_rejects_duplicate_name_invalid_version_and_empty_description(self):
        registry = ToolRegistry()
        register_test_tool(registry)

        with self.assertRaisesRegex(ToolValidationError, "already registered"):
            register_test_tool(registry)
        with self.assertRaisesRegex(ToolValidationError, "version"):
            register_test_tool(ToolRegistry(), version="v1")
        with self.assertRaisesRegex(ToolValidationError, "description"):
            register_test_tool(ToolRegistry(), description="  ")

    def test_registration_rejects_unsupported_schema_keyword_and_incomplete_safety_scope(self):
        invalid_schema = {**VALID_INPUT_SCHEMA, "oneOf": []}
        with self.assertRaisesRegex(ToolValidationError, "unsupported schema keyword 'oneOf'"):
            register_test_tool(ToolRegistry(), input_schema=invalid_schema)

        invalid_scope = dict(VALID_SAFETY_SCOPE)
        invalid_scope.pop("sideEffects")
        with self.assertRaisesRegex(ToolValidationError, "safetyScope.*sideEffects"):
            register_test_tool(ToolRegistry(), safety_scope=invalid_scope)

    def test_invoke_rejects_non_object_missing_unknown_empty_wrong_type_and_bounds(self):
        registry = ToolRegistry()
        register_test_tool(registry)

        invalid_cases = [
            ([], "tool 'search' input \\$: expected object"),
            ({}, "input \\$.query: required field is missing"),
            ({"query": "ok", "extra": True}, "input \\$.extra: unknown field"),
            ({"query": ""}, "input \\$.query: length must be at least 1"),
            ({"query": "ok", "limit": True}, "input \\$.limit: expected integer"),
            ({"query": "ok", "limit": 0}, "input \\$.limit: value must be at least 1"),
            ({"query": "ok", "limit": 11}, "input \\$.limit: value must be at most 10"),
        ]
        for payload, pattern in invalid_cases:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ToolValidationError, pattern):
                    registry.invoke("search", payload)

    def test_invoke_rejects_invalid_nested_output_with_field_path(self):
        registry = ToolRegistry()
        register_test_tool(registry, handler=lambda _payload: {"items": [{}]})

        with self.assertRaisesRegex(
            ToolValidationError,
            "tool 'search' output \\$.items\\[0\\].text: required field is missing",
        ):
            registry.invoke("search", {"query": "evidence"})

    def test_invoke_deep_copies_input_output_and_contracts(self):
        captured = {}
        handler_output = {"items": [{"text": "result"}]}

        def handler(payload):
            captured["payload"] = payload
            payload["query"] = "changed"
            return handler_output

        registry = ToolRegistry()
        definition = register_test_tool(registry, handler=handler)
        input_payload = {"query": "original"}

        result = registry.invoke("search", input_payload)
        result["items"][0]["text"] = "changed"

        self.assertEqual(input_payload["query"], "original")
        self.assertEqual(captured["payload"]["query"], "changed")
        self.assertEqual(handler_output["items"][0]["text"], "result")
        self.assertEqual(definition.version, "1.0.0")


    def test_descriptive_statistics_tool_has_restricted_versioned_contract(self):
        registry = get_tool_registry()
        contract = next(item for item in registry.list_tools() if item["name"] == "run_descriptive_statistics")

        self.assertEqual(contract["version"], "1.0.0")
        self.assertEqual(contract["inputSchema"], {
            "type": "object",
            "required": ["artifactId"],
            "properties": {
                "artifactId": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "additionalProperties": False,
        })
        self.assertEqual(contract["safetyScope"], {
            "access": "restricted",
            "dataScopes": ["code_execution_artifact"],
            "networkAccess": False,
            "sideEffects": True,
            "sensitiveOutput": True,
        })
        self.assertEqual(contract["outputSchema"]["required"], ["status", "jobId", "artifactId", "templateId"])
        self.assertFalse(contract["outputSchema"]["additionalProperties"])

    def test_descriptive_statistics_tool_input_validation_rejects_unsafe_inputs(self):
        registry = get_tool_registry()
        invalid_cases = [
            ({}, "required field is missing"),
            ({"artifactId": ""}, "length must be at least 1"),
            ({"artifactId": "a" * 129}, "maxLength"),
            ({"artifactId": "valid-id", "scriptText": "print(1)"}, "unknown field"),
            ({"artifactId": "valid-id", "templateId": "evil"}, "unknown field"),
        ]
        for payload, pattern in invalid_cases:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ToolValidationError, pattern):
                    registry.invoke("run_descriptive_statistics", payload)

    def test_descriptive_statistics_tool_rejects_invalid_artifact_ids(self):
        registry = get_tool_registry()
        malicious_ids = [
            "../../../etc/passwd",
            "/absolute/path/to/file",
            "C:\\Windows\\System32",
            "$(whoami)",
            "`rm -rf /`",
            "artifact; ls",
        ]
        for artifact_id in malicious_ids:
            with self.subTest(artifactId=artifact_id):
                with self.assertRaises(ToolValidationError):
                    registry.invoke("run_descriptive_statistics", {"artifactId": artifact_id})

    def test_descriptive_statistics_tool_creates_job_reference_with_fixed_template(self):
        import hashlib
        from code_worker import FIXED_TEMPLATE_TEXT

        registry = get_tool_registry()
        result = registry.invoke("run_descriptive_statistics", {"artifactId": "artifact-00000000000000000000000000000000"})

        self.assertEqual(result["status"], "awaiting_approval")
        self.assertTrue(result["jobId"])
        self.assertEqual(result["artifactId"], "artifact-00000000000000000000000000000000")
        self.assertEqual(result["templateId"], "descriptive-statistics-v1")
        self.assertIn("message", result)
        self.assertNotIn("scriptText", result)
        self.assertNotIn("scriptDigest", result)
        self.assertNotIn(FIXED_TEMPLATE_TEXT[:40], str(result))

    def test_descriptive_statistics_tool_never_accepts_script_text_from_payload(self):
        registry = get_tool_registry()
        for malicious_script in ["print('hello')", "import os; os.system('ls')", "", " " * 10]:
            with self.subTest(script=malicious_script[:40]):
                with self.assertRaises(ToolValidationError):
                    registry.invoke("run_descriptive_statistics", {
                        "artifactId": "artifact-test",
                        "scriptText": malicious_script,
                    })

    def test_descriptive_statistics_tool_is_not_exposed_through_mcp(self):
        registry = get_tool_registry()
        contract = next(item for item in registry.list_tools() if item["name"] == "run_descriptive_statistics")

        self.assertNotEqual(contract["safetyScope"]["access"], "read_only")
        self.assertTrue(contract["safetyScope"]["sideEffects"])

    def test_restricted_safety_scope_enforces_access_sideeffects_consistency(self):
        registry = ToolRegistry()
        inconsistent_cases = [
            ({"access": "restricted", "dataScopes": ["test"], "networkAccess": False, "sideEffects": False, "sensitiveOutput": True},
             r"sideEffects must be true"),
            ({"access": "read_only", "dataScopes": ["test"], "networkAccess": False, "sideEffects": True, "sensitiveOutput": True},
             r"sideEffects must be false"),
            ({"access": "execute", "dataScopes": ["test"], "networkAccess": False, "sideEffects": True, "sensitiveOutput": True},
             "unknown access"),
        ]
        for scope_dict, expected_pattern in inconsistent_cases:
            with self.subTest(scope=scope_dict):
                with self.assertRaisesRegex(ToolValidationError, expected_pattern):
                    registry.register(
                        name="inconsistent_tool",
                        version="1.0.0",
                        description="Should be rejected.",
                        input_schema=VALID_INPUT_SCHEMA,
                        handler=lambda p: {"items": []},
                        output_schema=VALID_OUTPUT_SCHEMA,
                        safety_scope=scope_dict,
                    )

    def test_existing_tools_keep_read_only_safety_scopes(self):
        registry = get_tool_registry()
        restricted_tools = {"run_descriptive_statistics", "execute_python", "query_structured_data", "search_web", "fetch_web_page"}
        for contract in registry.list_tools():
            if contract["name"] in restricted_tools:
                continue
            self.assertEqual(
                contract["safetyScope"]["access"], "read_only",
                f"{contract['name']} must remain read_only",
            )
            self.assertFalse(
                contract["safetyScope"]["sideEffects"],
                f"{contract['name']} must remain sideEffects=false",
            )

    def test_search_web_tool_is_registered_with_restricted_contract(self):
        registry = get_tool_registry()
        definition = registry.get("search_web")

        self.assertEqual(definition.name, "search_web")
        self.assertEqual(definition.version, "1.0.0")
        self.assertEqual(definition.safetyScope["access"], "restricted")
        self.assertTrue(definition.safetyScope["networkAccess"])
        self.assertTrue(definition.safetyScope["sideEffects"])
        self.assertTrue(definition.safetyScope["sensitiveOutput"])
        self.assertEqual(definition.safetyScope["dataScopes"], ["web_search_results"])

        # Input schema
        props = definition.inputSchema["properties"]
        self.assertIn("query", props)
        self.assertEqual(props["query"]["minLength"], 1)
        self.assertEqual(props["query"]["maxLength"], 300)
        self.assertIn("limit", props)
        self.assertEqual(props["limit"]["minimum"], 1)
        self.assertEqual(props["limit"]["maximum"], 10)
        self.assertIn("searchType", props)
        self.assertEqual(props["searchType"]["enum"], ["general", "academic", "news"])
        self.assertFalse(definition.inputSchema["additionalProperties"])

        # Output schema
        self.assertEqual(
            definition.outputSchema["properties"]["status"]["enum"],
            ["disabled", "success", "budget_exceeded", "failed"],
        )
        self.assertFalse(definition.outputSchema["additionalProperties"])

    def test_fetch_web_page_tool_is_registered_with_restricted_contract(self):
        registry = get_tool_registry()
        definition = registry.get("fetch_web_page")

        self.assertEqual(definition.name, "fetch_web_page")
        self.assertEqual(definition.version, "1.0.0")
        self.assertEqual(definition.safetyScope["access"], "restricted")
        self.assertTrue(definition.safetyScope["networkAccess"])
        self.assertTrue(definition.safetyScope["sideEffects"])
        self.assertEqual(definition.safetyScope["dataScopes"], ["web_page_content"])

        props = definition.inputSchema["properties"]
        self.assertIn("url", props)
        self.assertEqual(props["url"]["minLength"], 1)
        self.assertEqual(props["url"]["maxLength"], 2048)
        self.assertIn("maxChars", props)
        self.assertEqual(props["maxChars"]["minimum"], 1000)
        self.assertEqual(props["maxChars"]["maximum"], 16000)
        self.assertFalse(definition.inputSchema["additionalProperties"])

        self.assertEqual(
            definition.outputSchema["properties"]["status"]["enum"],
            ["success", "disabled", "budget_exceeded", "failed"],
        )
        self.assertFalse(definition.outputSchema["additionalProperties"])

    def test_execute_python_tool_has_restricted_versioned_contract(self):
        registry = get_tool_registry()
        definition = registry.get("execute_python")

        self.assertEqual(definition.name, "execute_python")
        self.assertEqual(definition.version, "1.0.0")
        self.assertEqual(definition.safetyScope["access"], "restricted")
        self.assertFalse(definition.safetyScope["networkAccess"])
        self.assertTrue(definition.safetyScope["sideEffects"])
        self.assertTrue(definition.safetyScope["sensitiveOutput"])
        self.assertEqual(definition.safetyScope["dataScopes"], ["code_execution"])

        # Input schema
        props = definition.inputSchema["properties"]
        self.assertIn("code", props)
        self.assertEqual(props["code"]["minLength"], 1)
        self.assertEqual(props["code"]["maxLength"], 65536)
        self.assertIn("timeout", props)
        self.assertEqual(props["timeout"]["minimum"], 1)
        self.assertEqual(props["timeout"]["maximum"], 30)
        self.assertFalse(definition.inputSchema["additionalProperties"])

        # Output schema
        self.assertEqual(
            definition.outputSchema["required"],
            ["status", "stdout", "stderr", "error"],
        )
        self.assertEqual(
            definition.outputSchema["properties"]["status"]["enum"],
            ["success", "timeout", "error", "forbidden_import"],
        )
        self.assertFalse(definition.outputSchema["additionalProperties"])

    def test_execute_python_tool_rejects_empty_code(self):
        registry = get_tool_registry()
        # Missing code → schema validation error.
        with self.assertRaisesRegex(ToolValidationError, "required field"):
            registry.invoke("execute_python", {})
        # Empty / whitespace-only → schema catches minLength (value is stripped before check).
        for code_val in ("", "   "):
            with self.subTest(code=code_val):
                with self.assertRaisesRegex(ToolValidationError, "length must be at least"):
                    registry.invoke("execute_python", {"code": code_val})

    def test_execute_python_tool_rejects_code_exceeding_max_length(self):
        registry = get_tool_registry()
        long_code = "x" * 65537
        with self.assertRaisesRegex(ToolValidationError, "maxLength"):
            registry.invoke("execute_python", {"code": long_code})

    def test_execute_python_tool_timeout_range(self):
        registry = get_tool_registry()
        too_low = {"code": "print(1)", "timeout": 0}
        too_high = {"code": "print(1)", "timeout": 31}
        with self.assertRaisesRegex(ToolValidationError, "must be at least"):
            registry.invoke("execute_python", too_low)
        with self.assertRaisesRegex(ToolValidationError, "must be at most"):
            registry.invoke("execute_python", too_high)

    def test_execute_python_tool_rejects_unknown_fields(self):
        registry = get_tool_registry()
        for payload in [
            {"code": "print(1)", "scriptText": "evil"},
            {"code": "print(1)", "unsafe": True},
        ]:
            with self.subTest(payload=payload):
                with self.assertRaises(ToolValidationError):
                    registry.invoke("execute_python", payload)

    def test_execute_python_tool_is_not_exposed_through_mcp(self):
        registry = get_tool_registry()
        definition = registry.get("execute_python")
        self.assertNotEqual(definition.safetyScope["access"], "read_only")
        self.assertTrue(definition.safetyScope["sideEffects"])

    def test_query_structured_data_tool_has_restricted_versioned_contract(self):
        registry = get_tool_registry()
        definition = registry.get("query_structured_data")

        self.assertEqual(definition.name, "query_structured_data")
        self.assertEqual(definition.version, "1.0.0")
        self.assertEqual(definition.safetyScope["access"], "restricted")
        self.assertFalse(definition.safetyScope["networkAccess"])
        self.assertTrue(definition.safetyScope["sideEffects"])
        self.assertTrue(definition.safetyScope["sensitiveOutput"])
        self.assertEqual(definition.safetyScope["dataScopes"], ["structured_query"])

        # Input schema
        props = definition.inputSchema["properties"]
        self.assertIn("query", props)
        self.assertEqual(props["query"]["minLength"], 1)
        self.assertEqual(props["query"]["maxLength"], 4096)
        self.assertIn("data", props)
        self.assertEqual(props["data"]["minLength"], 1)
        self.assertEqual(props["data"]["maxLength"], 524288)
        self.assertFalse(definition.inputSchema["additionalProperties"])

        # Output schema
        self.assertEqual(
            definition.outputSchema["required"],
            ["status", "rows", "rowCount", "error"],
        )
        self.assertEqual(
            definition.outputSchema["properties"]["status"]["enum"],
            ["success", "error"],
        )
        self.assertFalse(definition.outputSchema["additionalProperties"])

    def test_query_structured_data_tool_rejects_empty_query(self):
        registry = get_tool_registry()
        # Missing query → schema validation error.
        with self.assertRaisesRegex(ToolValidationError, "required field"):
            registry.invoke("query_structured_data", {"data": "[]"})
        # Empty query → schema catches minLength (value is stripped before check).
        with self.assertRaisesRegex(ToolValidationError, "length must be at least"):
            registry.invoke("query_structured_data", {"query": "", "data": "[]"})

    def test_query_structured_data_tool_rejects_non_select(self):
        registry = get_tool_registry()
        result = registry.invoke("query_structured_data", {
            "query": "DROP TABLE data",
            "data": '[{"x": 1}]',
        })
        self.assertEqual(result["status"], "error")
        self.assertIn("Only SELECT", result["error"])

    def test_query_structured_data_tool_is_not_exposed_through_mcp(self):
        registry = get_tool_registry()
        definition = registry.get("query_structured_data")
        self.assertNotEqual(definition.safetyScope["access"], "read_only")
        self.assertTrue(definition.safetyScope["sideEffects"])


if __name__ == "__main__":
    unittest.main()
