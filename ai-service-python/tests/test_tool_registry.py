import json
import unittest

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
        reset_tool_registry()

    def test_default_registry_exposes_seven_serializable_versioned_contracts(self):
        registry = get_tool_registry()

        contracts = registry.list_tools()

        self.assertEqual(registry.schemaVersion, "1.0")
        self.assertEqual(len(contracts), 7)
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


if __name__ == "__main__":
    unittest.main()
