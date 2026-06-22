import asyncio
import json
import os
import unittest
from io import StringIO
from unittest.mock import Mock, patch

from services.tool_registry import ToolValidationError, get_tool_registry


class McpAdapterTests(unittest.TestCase):
    def test_entrypoint_refuses_to_start_when_disabled(self):
        from mcp_adapter.__main__ import main

        runner = Mock()
        stderr = StringIO()
        with patch.dict(os.environ, {}, clear=True):
            exit_code = main(run_server=runner, stderr=stderr)

        self.assertEqual(exit_code, 2)
        self.assertIn("PIXIU_MCP_ENABLED=true", stderr.getvalue())
        runner.assert_not_called()

    def test_entrypoint_runs_stdio_server_when_enabled(self):
        from mcp_adapter.__main__ import main

        runner = Mock()
        with patch.dict(os.environ, {"PIXIU_MCP_ENABLED": "true"}, clear=True):
            exit_code = main(run_server=runner)

        self.assertEqual(exit_code, 0)
        runner.assert_called_once_with()

    def test_adapter_is_disabled_unless_explicitly_enabled(self):
        from mcp_adapter.adapter import is_mcp_enabled

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_mcp_enabled())
        for enabled_value in ("true", "TRUE", "1", "yes", "on"):
            with self.subTest(enabled_value=enabled_value):
                with patch.dict(os.environ, {"PIXIU_MCP_ENABLED": enabled_value}, clear=True):
                    self.assertTrue(is_mcp_enabled())

    def test_list_tools_exposes_only_allowlisted_contracts_with_read_only_metadata(self):
        from mcp_adapter.adapter import MCP_ALLOWED_TOOL_NAMES, list_mcp_tools

        registry = get_tool_registry()
        internal_contracts = {item["name"]: item for item in registry.list_tools()}

        tools = list_mcp_tools(registry)

        self.assertEqual({tool["name"] for tool in tools}, set(MCP_ALLOWED_TOOL_NAMES))
        for tool in tools:
            internal = internal_contracts[tool["name"]]
            self.assertEqual(tool["description"], internal["description"])
            self.assertEqual(tool["inputSchema"], internal["inputSchema"])
            self.assertEqual(tool["outputSchema"], internal["outputSchema"])
            self.assertEqual(tool["_meta"]["pixiu"]["version"], internal["version"])
            self.assertEqual(tool["_meta"]["pixiu"]["safetyScope"], internal["safetyScope"])
            self.assertEqual(tool["_meta"]["pixiu"]["schemaVersion"], registry.schemaVersion)
            self.assertEqual(
                tool["annotations"],
                {
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "idempotentHint": True,
                    "openWorldHint": False,
                },
            )

    def test_call_tool_uses_registry_invoke_and_returns_text_and_structured_content(self):
        from mcp_adapter.adapter import call_mcp_tool

        registry = Mock()
        registry.invoke.return_value = {"items": [{"sourceId": "paper-1", "text": "evidence"}]}

        result = call_mcp_tool(
            "retrieve_library",
            {"query": "method", "topK": 5, "limit": 4, "maxTextChars": 700},
            registry,
        )

        registry.invoke.assert_called_once_with(
            "retrieve_library",
            {"query": "method", "topK": 5, "limit": 4, "maxTextChars": 700},
        )
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"], registry.invoke.return_value)
        self.assertEqual(json.loads(result["content"][0]["text"]), registry.invoke.return_value)

    def test_call_tool_rejects_unknown_and_non_allowlisted_tools(self):
        from mcp_adapter.adapter import call_mcp_tool

        registry = Mock()
        for name in ("missing", "translate_page", "run_critical_analysis", "retrieve_external_academic"):
            with self.subTest(name=name):
                result = call_mcp_tool(name, {}, registry)
                self.assertTrue(result["isError"])
                self.assertIn("not available", result["content"][0]["text"])
        registry.invoke.assert_not_called()

    def test_call_tool_preserves_validation_field_path(self):
        from mcp_adapter.adapter import call_mcp_tool

        registry = Mock()
        registry.invoke.side_effect = ToolValidationError(
            "tool 'read_paper_skeleton' input $.unexpected: unknown field."
        )

        result = call_mcp_tool("read_paper_skeleton", {"unexpected": True}, registry)

        self.assertTrue(result["isError"])
        self.assertEqual(
            result["content"][0]["text"],
            "tool 'read_paper_skeleton' input $.unexpected: unknown field.",
        )

    def test_current_paper_retrieval_rejects_full_export_and_excessive_budgets(self):
        from mcp_adapter.adapter import call_mcp_tool

        invalid_payloads = [
            ({"pdfId": "paper-1", "query": "method", "includeAll": True}, "includeAll"),
            ({"pdfId": "paper-1", "query": "method", "topK": 9}, "topK"),
            ({"pdfId": "paper-1", "query": "method", "limit": 6}, "limit"),
            ({"pdfId": "paper-1", "query": "method", "maxTextChars": 901}, "maxTextChars"),
        ]
        registry = Mock()

        for payload, field in invalid_payloads:
            with self.subTest(field=field):
                result = call_mcp_tool("retrieve_current_paper", payload, registry)
                self.assertTrue(result["isError"])
                self.assertIn(f"$.{field}", result["content"][0]["text"])
        registry.invoke.assert_not_called()

    def test_library_and_skeleton_reject_excessive_budgets(self):
        from mcp_adapter.adapter import call_mcp_tool

        invalid_calls = [
            ("retrieve_library", {"query": "method", "topK": 6}, "topK"),
            ("retrieve_library", {"query": "method", "limit": 5}, "limit"),
            ("retrieve_library", {"query": "method", "maxTextChars": 701}, "maxTextChars"),
            ("read_paper_skeleton", {"paperSkeleton": {}, "maxSections": 7}, "maxSections"),
            ("read_paper_skeleton", {"paperSkeleton": {}, "maxCharsPerSection": 221}, "maxCharsPerSection"),
        ]
        registry = Mock()

        for name, payload, field in invalid_calls:
            with self.subTest(name=name, field=field):
                result = call_mcp_tool(name, payload, registry)
                self.assertTrue(result["isError"])
                self.assertIn(f"$.{field}", result["content"][0]["text"])
        registry.invoke.assert_not_called()

    def test_runtime_errors_are_sanitized(self):
        from mcp_adapter.adapter import call_mcp_tool

        registry = Mock()
        registry.invoke.side_effect = RuntimeError(
            "API key sk-secret failed at C:\\private\\trace_service.py:42"
        )

        result = call_mcp_tool("read_paper_skeleton", {"paperSkeleton": {}}, registry)

        self.assertTrue(result["isError"])
        message = result["content"][0]["text"]
        self.assertEqual(message, "Tool 'read_paper_skeleton' failed safely.")
        self.assertNotIn("sk-secret", message)
        self.assertNotIn("trace_service", message)

    def test_protocol_list_handler_serializes_contract_extensions(self):
        import mcp.types as types

        from mcp_adapter.server import build_server

        server = build_server(get_tool_registry())
        handler = server.request_handlers[types.ListToolsRequest]

        response = asyncio.run(handler(types.ListToolsRequest(method="tools/list")))
        serialized = [tool.model_dump(by_alias=True, exclude_none=True) for tool in response.root.tools]

        self.assertEqual(len(serialized), 3)
        self.assertTrue(all("outputSchema" in tool for tool in serialized))
        self.assertTrue(all(tool["_meta"]["pixiu"]["version"] == "1.0.0" for tool in serialized))

    def test_protocol_call_handler_returns_structured_result_and_tool_error(self):
        import mcp.types as types

        from mcp_adapter.server import build_server

        registry = Mock()
        registry.list_tools.return_value = get_tool_registry().list_tools()
        registry.schemaVersion = "1.0"
        registry.invoke.return_value = {"text": "Introduction: summary", "sections": []}
        server = build_server(registry)
        handler = server.request_handlers[types.CallToolRequest]

        success = asyncio.run(handler(types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(
                name="read_paper_skeleton",
                arguments={"paperSkeleton": {"Introduction": "summary"}},
            ),
        )))
        denied = asyncio.run(handler(types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(name="translate_page", arguments={}),
        )))

        self.assertFalse(success.root.isError)
        self.assertEqual(success.root.model_dump()["structuredContent"], registry.invoke.return_value)
        self.assertTrue(denied.root.isError)
        self.assertNotIn("structuredContent", denied.root.model_dump(exclude_none=True))


if __name__ == "__main__":
    unittest.main()
