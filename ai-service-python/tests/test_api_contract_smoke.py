import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from routes import api
from schemas.requests import (
    AgentFinalReviewRequest,
    AgentPlanItemRequest,
    AgentPlanReviewRequest,
    AgentProjectCreateRequest,
    AgentTaskCreateRequest,
    BackgroundKnowledgeRequest,
    ChatRequest,
    DeepAnalysisRequest,
    ResearchFinalReviewRequest,
    ResearchPlanReviewRequest,
    ResearchTaskCreateRequest,
)


CONTRACT_PATH = Path(__file__).parents[2] / "contracts" / "api-contract-smoke.json"


def _assert_contract(value, schema, path="response"):
    expected_type = schema.get("type")
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "null": type(None),
    }
    if expected_type:
        unittest.TestCase().assertIsInstance(value, type_map[expected_type], path)
    if "enum" in schema:
        unittest.TestCase().assertIn(value, schema["enum"], path)
    if expected_type == "object":
        for key in schema.get("required", []):
            unittest.TestCase().assertIn(key, value, f"{path}.{key}")
        for key, child_schema in schema.get("properties", {}).items():
            if key in value:
                _assert_contract(value[key], child_schema, f"{path}.{key}")
    if expected_type == "array" and schema.get("items"):
        for index, item in enumerate(value):
            _assert_contract(item, schema["items"], f"{path}[{index}]")


class ApiContractSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.operations = {item["operation"]: item for item in cls.contract["operations"]}

    def test_contract_covers_required_cross_service_operations(self):
        self.assertEqual(self.contract["schemaVersion"], 1)
        self.assertEqual(
            set(self.operations),
            {
                "chat",
                "critical",
                "background",
                "research",
                "research-plan-review",
                "research-task",
                "research-final-review",
                "trace",
                "agent-projects",
                "agent-tasks",
                "agent-plan-review",
                "agent-task",
                "agent-final-review",
                "agent-traces",
            },
        )

    def test_fastapi_routes_and_request_models_match_shared_contract(self):
        route_methods = {
            (route.path, method)
            for route in api.router.routes
            for method in (route.methods or set())
        }
        request_models = {
            "chat": ChatRequest,
            "critical": DeepAnalysisRequest,
            "background": BackgroundKnowledgeRequest,
            "research": ResearchTaskCreateRequest,
            "research-plan-review": ResearchPlanReviewRequest,
            "research-final-review": ResearchFinalReviewRequest,
            "agent-projects": AgentProjectCreateRequest,
            "agent-tasks": AgentTaskCreateRequest,
            "agent-plan-review": AgentPlanReviewRequest,
            "agent-final-review": AgentFinalReviewRequest,
        }

        for operation, fixture in self.operations.items():
            with self.subTest(operation=operation):
                self.assertIn((fixture["pythonPath"], fixture["method"]), route_methods)
                if operation in request_models:
                    request_models[operation].model_validate(fixture["pythonRequest"])

    def test_fastapi_responses_match_shared_required_field_contracts(self):
        invocations = {
            "chat": (api.chat, ChatRequest, "chat_service.chat", ()),
            "critical": (api.deep_analysis, DeepAnalysisRequest, "analysis_service.deep_analysis", ()),
            "background": (
                api.background_knowledge,
                BackgroundKnowledgeRequest,
                "analysis_service.get_background_knowledge",
                (),
            ),
            "research": (
                api.create_research_task,
                ResearchTaskCreateRequest,
                "research_task_service.create_research_task",
                (),
            ),
            "research-plan-review": (
                api.review_research_plan,
                ResearchPlanReviewRequest,
                "research_task_service.review_research_plan",
                ("research-task-contract-1",),
            ),
            "research-task": (
                api.get_research_task,
                None,
                "research_task_service.get_research_task",
                ("research-task-contract-1",),
            ),
            "research-final-review": (
                api.review_research_final,
                ResearchFinalReviewRequest,
                "research_task_service.review_research_final",
                ("research-task-contract-1",),
            ),
            "trace": (api.get_trace, None, "trace_service.get_trace_summary", ("trace-contract-1",)),
            "agent-projects": (
                api.create_agent_project,
                AgentProjectCreateRequest,
                "agent_project_service.create_agent_project",
                (),
            ),
            "agent-tasks": (
                api.create_agent_task,
                AgentTaskCreateRequest,
                "agent_project_service.create_agent_task",
                ("project-contract-1",),
            ),
            "agent-plan-review": (
                api.review_agent_plan,
                AgentPlanReviewRequest,
                "agent_project_service.review_agent_plan",
                ("agent-task-contract-1",),
            ),
            "agent-task": (
                api.get_agent_task,
                None,
                "agent_project_service.get_agent_task",
                ("agent-task-contract-1",),
            ),
            "agent-final-review": (
                api.review_agent_final,
                AgentFinalReviewRequest,
                "agent_project_service.review_agent_final",
                ("agent-task-contract-1",),
            ),
            "agent-traces": (
                api.get_agent_trace,
                None,
                "trace_service.get_trace_summary",
                ("agent-trace-contract-1",),
            ),
        }

        for operation, fixture in self.operations.items():
            route_function, model, patch_target, path_args = invocations[operation]
            args = list(path_args)
            if model is not None:
                args.append(model.model_validate(fixture["pythonRequest"]))
            with self.subTest(operation=operation), patch.object(
                api,
                patch_target.split(".")[0],
            ) as service_module:
                getattr(service_module, patch_target.split(".")[1]).return_value = fixture["pythonResponse"]
                response = asyncio.run(route_function(*args))
                payload = json.loads(response.body)
                self.assertEqual(response.status_code, fixture["statusCode"])
                _assert_contract(payload, fixture["pythonResponseContract"])


    def test_research_task_create_request_allow_external_search_defaults_false(self):
        req = ResearchTaskCreateRequest(question="测试", pdfId="paper-1")
        self.assertFalse(req.allowExternalSearch)

        req_enabled = ResearchTaskCreateRequest(question="测试", pdfId="paper-1", allowExternalSearch=True)
        self.assertTrue(req_enabled.allowExternalSearch)

    def test_research_task_create_request_allow_council_defaults_false(self):
        req = ResearchTaskCreateRequest(question="测试", pdfId="paper-1")
        self.assertFalse(req.allowCouncil)

        req_enabled = ResearchTaskCreateRequest(question="测试", pdfId="paper-1", allowCouncil=True)
        self.assertTrue(req_enabled.allowCouncil)

    def test_shared_contract_carries_allow_council_and_council_snapshot(self):
        create_fixture = self.operations["research"]
        self.assertFalse(create_fixture["frontendRequest"]["allowCouncil"])
        self.assertFalse(create_fixture["pythonRequest"]["allowCouncil"])
        self.assertIn("council", create_fixture["pythonResponse"]["task"])
        self.assertIn("council", create_fixture["gatewayResponse"]["task"])

        task_fixture = self.operations["research-task"]
        self.assertIn("council", task_fixture["pythonResponse"]["task"])
        self.assertIn("council", task_fixture["gatewayResponse"]["task"])

    def test_agent_task_create_request_allow_external_search_defaults_false(self):
        req = AgentTaskCreateRequest(prompt="测试")
        self.assertFalse(req.allowExternalSearch)

        req_enabled = AgentTaskCreateRequest(prompt="测试", allowExternalSearch=True)
        self.assertTrue(req_enabled.allowExternalSearch)

    def test_agent_plan_item_allow_external_search_defaults_false(self):
        item = AgentPlanItemRequest(label="测试")
        self.assertFalse(item.allowExternalSearch)

        item_enabled = AgentPlanItemRequest(label="测试", allowExternalSearch=True)
        self.assertTrue(item_enabled.allowExternalSearch)


if __name__ == "__main__":
    unittest.main()
