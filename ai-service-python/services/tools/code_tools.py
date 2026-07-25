"""Code execution and data analysis tools.

This module registers tools related to code execution (Python sandbox,
descriptive statistics), structured data querying, image/chart analysis,
browser automation, HTML table extraction, and meta-analysis.
"""

from typing import Any

from code_worker import FIXED_TEMPLATE_TEXT
from services.browser_agent import browser_navigate, browser_screenshot
from services.chart_analyzer import extract_chart_data
from services.code_execution_models import IDENTIFIER_PATTERN, create_code_execution_job
from services.code_executor import execute_python_sandbox
from services.image_analyzer import analyze_image
from services.meta_analysis import meta_analyze
from services.structured_query import query_structured_data
from services.table_extractor import extract_html_tables
from services.tool_registry import ToolValidationError, _safety_scope
from services.tools._common import _clean_text
from services.trace_service import record_counter, trace_step


def register_tools(registry) -> None:
    registry.register(
        "run_descriptive_statistics",
        "Create a sandboxed descriptive-statistics job for an approved CSV artifact. "
        "Execution requires human approval and runs without network access.",
        {
            "type": "object",
            "required": ["artifactId"],
            "properties": {
                "artifactId": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "additionalProperties": False,
        },
        _run_descriptive_statistics_tool,
        output_schema={
            "type": "object",
            "required": ["status", "jobId", "artifactId", "templateId"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": [
                        "awaiting_approval", "approved", "queued", "running",
                        "succeeded", "failed", "cancelled", "rejected",
                    ],
                },
                "jobId": {"type": "string", "minLength": 1},
                "artifactId": {"type": "string", "minLength": 1},
                "templateId": {"type": "string"},
                "statistics": {"type": "object"},
                "message": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["code_execution_artifact"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "execute_python",
        "Execute a short Python script in a restricted sandbox. "
        "Only a whitelist of safe standard-library modules is available: "
        "math, statistics, json, csv, collections, itertools, datetime, re, "
        "textwrap, pprint, and similar. "
        "Network access, filesystem writes, and dangerous built-ins "
        "(eval, exec, __import__, open, etc.) are blocked. "
        "Maximum 30 second timeout.",
        {
            "type": "object",
            "required": ["code"],
            "properties": {
                "code": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 65536,
                },
                "timeout": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                },
            },
            "additionalProperties": False,
        },
        _execute_python_tool,
        output_schema={
            "type": "object",
            "required": ["status", "stdout", "stderr", "error"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["success", "timeout", "error", "forbidden_import"],
                },
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["code_execution"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "query_structured_data",
        "Execute a SQL SELECT query against a JSON array of objects in an "
        "in-memory sandbox. Supports SELECT, WHERE, ORDER BY, GROUP BY, and "
        "LIMIT. No external database connection -- the data is loaded from "
        "the `data` JSON parameter and discarded after the query. "
        "Only SELECT statements are allowed; write operations are rejected.",
        {
            "type": "object",
            "required": ["query", "data"],
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4096,
                },
                "data": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 524288,
                },
            },
            "additionalProperties": False,
        },
        _query_structured_data_tool,
        output_schema={
            "type": "object",
            "required": ["status", "rows", "rowCount", "error"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["success", "error"],
                },
                "rows": {
                    "type": "array",
                    "items": {"type": "object", "additionalProperties": True},
                },
                "rowCount": {"type": "integer", "minimum": 0},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["structured_query"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "analyze_image",
        "Download an image from a whitelisted URL and analyze it with a "
        "vision-capable LLM. Returns a text description of the image content. "
        "The description is tagged with sourceType='image_analysis' for "
        "evidence-chain integration. Images are not cached or persisted.",
        {
            "type": "object",
            "required": ["imageUrl"],
            "properties": {
                "imageUrl": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2048,
                },
            },
            "additionalProperties": False,
        },
        _analyze_image_tool,
        output_schema={
            "type": "object",
            "required": ["status", "description", "imageUrl", "sourceType", "error"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["success", "error"],
                },
                "description": {"type": "string"},
                "imageUrl": {"type": "string"},
                "sourceType": {"type": "string"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["image_analysis"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "browser_navigate",
        "Navigate to a whitelisted URL using a headless browser (Playwright Chromium) "
        "and return the JS-rendered text content. The browser session is maintained "
        "across calls. Use this for pages that require JavaScript to render content. "
        "Controlled by the PIXIU_ALLOW_BROWSER environment variable (default: disabled).",
        {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2048,
                },
            },
            "additionalProperties": False,
        },
        _browser_navigate_tool,
        output_schema={
            "type": "object",
            "required": ["status", "url", "content", "title", "error"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["success", "error"],
                },
                "url": {"type": "string"},
                "content": {"type": "string"},
                "title": {"type": "string"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["browser_content"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "browser_screenshot",
        "Capture a screenshot of the current headless browser page viewport "
        "as a base64-encoded PNG data URI. Requires a prior browser_navigate call. "
        "Controlled by the PIXIU_ALLOW_BROWSER environment variable (default: disabled).",
        {
            "type": "object",
            "required": [],
            "properties": {},
            "additionalProperties": False,
        },
        _browser_screenshot_tool,
        output_schema={
            "type": "object",
            "required": ["status", "imageBase64", "error"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["success", "error"],
                },
                "imageBase64": {"type": "string"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["browser_screenshot"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "extract_chart_data",
        "Extract structured quantitative data from a chart image. "
        "Returns chart type, axis labels, data series with data points and "
        "error bars, legend items, and caption. Uses VLM with specialized "
        "chart-reading prompts.",
        {
            "type": "object",
            "required": ["imageUrl"],
            "properties": {
                "imageUrl": {"type": "string", "minLength": 1, "maxLength": 2048},
            },
            "additionalProperties": False,
        },
        _extract_chart_data_tool,
        output_schema={
            "type": "object",
            "required": ["status", "chartType", "dataSeries", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "chartType": {"type": "string"},
                "title": {"type": "string"},
                "dataSeries": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "summary": {"type": "string"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["chart_analysis"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "extract_html_tables",
        "Extract structured table data from raw HTML content. "
        "Finds <table> elements, parses headers and rows, returns JSON arrays "
        "compatible with query_structured_data.",
        {
            "type": "object",
            "required": ["html"],
            "properties": {
                "html": {"type": "string", "minLength": 1, "maxLength": 524288},
            },
            "additionalProperties": False,
        },
        _extract_html_tables_tool,
        output_schema={
            "type": "object",
            "required": ["status", "tables", "tableCount", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "tables": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "tableCount": {"type": "integer", "minimum": 0},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["table_extraction"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "meta_analyze",
        "Perform mini meta-analysis across multiple studies. Aggregates effect "
        "sizes using random-effects (DerSimonian-Laird) and fixed-effects models, "
        "computes heterogeneity (Q, I^2), Egger's test for publication bias, "
        "and GRADE evidence quality assessment. Returns forest plot data.",
        {
            "type": "object",
            "required": ["studies"],
            "properties": {
                "studies": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            "additionalProperties": False,
        },
        _meta_analyze_tool,
        output_schema={
            "type": "object",
            "required": ["status", "summary", "heterogeneity", "forestPlot", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "model": {"type": "string"},
                "summary": {"type": "object", "additionalProperties": True},
                "heterogeneity": {"type": "object", "additionalProperties": True},
                "forestPlot": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "studyCount": {"type": "integer", "minimum": 0},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["meta_analysis"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )


def _run_descriptive_statistics_tool(payload: dict[str, Any]) -> dict[str, Any]:
    artifact_id = _clean_text(payload.get("artifactId"))
    if not artifact_id:
        raise ToolValidationError("run_descriptive_statistics requires a non-empty artifactId.")
    if not IDENTIFIER_PATTERN.fullmatch(artifact_id):
        raise ToolValidationError(
            "run_descriptive_statistics artifactId must be an opaque identifier, not a path or URI."
        )
    if len(artifact_id) > 128:
        raise ToolValidationError("run_descriptive_statistics artifactId exceeds maximum length.")

    script_text = FIXED_TEMPLATE_TEXT

    with trace_step("tool_run_descriptive_statistics", input_size=len(artifact_id)) as step:
        job = create_code_execution_job(
            job_id=f"job-{artifact_id}",
            artifact_id=artifact_id,
            artifact_digest="0" * 64,
            script_text=script_text,
        )
        step["outputSize"] = 1
        return {
            "status": job.status,
            "jobId": job.job_id,
            "artifactId": artifact_id,
            "templateId": job.runtime.template_id,
            "message": "Job created. Requires execution approval before the sandbox runs.",
        }


def _execute_python_tool(payload: dict[str, Any]) -> dict[str, Any]:
    code = (payload.get("code") or "").strip()
    if not code:
        raise ToolValidationError("execute_python requires a non-empty code string.")
    if len(code) > 65536:
        raise ToolValidationError(
            f"execute_python code length {len(code)} exceeds maximum 65536 characters."
        )

    timeout = int(payload.get("timeout") or 30)
    timeout = min(max(timeout, 1), 30)

    with trace_step("tool_execute_python", input_size=len(code)) as step:
        record_counter("codeExecutionCalls")
        try:
            result = execute_python_sandbox(code, timeout=timeout)
        except ValueError as exc:
            raise ToolValidationError(str(exc)) from exc
        step["outputSize"] = len(result.get("stdout") or "") + len(result.get("stderr") or "")
        step["meta"] = {
            "status": result["status"],
            "outputChars": step["outputSize"],
        }
        if result["status"] != "success":
            record_counter("codeExecutionFailures")
        return result


def _query_structured_data_tool(payload: dict[str, Any]) -> dict[str, Any]:
    query = (payload.get("query") or "").strip()
    if not query:
        raise ToolValidationError("query_structured_data requires a non-empty query string.")
    data = (payload.get("data") or "").strip()
    if not data:
        raise ToolValidationError("query_structured_data requires a non-empty data string.")

    with trace_step("tool_query_structured_data", input_size=len(data)) as step:
        record_counter("structuredQueryCalls")
        try:
            result = query_structured_data(query, data)
        except ValueError as exc:
            raise ToolValidationError(str(exc)) from exc
        step["outputSize"] = result.get("rowCount", 0)
        step["meta"] = {
            "status": result["status"],
            "rowCount": result["rowCount"],
        }
        if result["status"] != "success":
            record_counter("structuredQueryFailures")
        return result


def _analyze_image_tool(payload: dict[str, Any]) -> dict[str, Any]:
    image_url = (payload.get("imageUrl") or "").strip()
    if not image_url:
        raise ToolValidationError("analyze_image requires a non-empty imageUrl.")

    with trace_step("tool_analyze_image", input_size=len(image_url)) as step:
        record_counter("imageAnalysisCalls")
        try:
            result = analyze_image(image_url)
        except ValueError as exc:
            raise ToolValidationError(str(exc)) from exc
        step["outputSize"] = len(result.get("description") or "")
        step["meta"] = {
            "status": result["status"],
            "sourceType": result.get("sourceType"),
        }
        if result["status"] != "success":
            record_counter("imageAnalysisFailures")
        return result


def _browser_navigate_tool(payload: dict[str, Any]) -> dict[str, Any]:
    url = (payload.get("url") or "").strip()
    if not url:
        raise ToolValidationError("browser_navigate requires a non-empty url.")

    with trace_step("tool_browser_navigate", input_size=len(url)) as step:
        record_counter("browserNavigateCalls")
        try:
            result = browser_navigate(url)
        except ValueError as exc:
            raise ToolValidationError(str(exc)) from exc
        step["outputSize"] = len(result.get("content") or "")
        step["meta"] = {"status": result["status"]}
        if result["status"] != "success":
            record_counter("browserNavigateFailures")
        return result


def _browser_screenshot_tool(payload: dict[str, Any]) -> dict[str, Any]:
    with trace_step("tool_browser_screenshot", input_size=0) as step:
        record_counter("browserScreenshotCalls")
        try:
            result = browser_screenshot()
        except ValueError as exc:
            raise ToolValidationError(str(exc)) from exc
        step["outputSize"] = len(result.get("imageBase64") or "")
        step["meta"] = {"status": result["status"]}
        if result["status"] != "success":
            record_counter("browserScreenshotFailures")
        return result


def _extract_chart_data_tool(payload: dict[str, Any]) -> dict[str, Any]:
    image_url = (payload.get("imageUrl") or "").strip()
    if not image_url:
        raise ToolValidationError("extract_chart_data requires a non-empty imageUrl.")
    with trace_step("tool_extract_chart_data", input_size=len(image_url)) as step:
        record_counter("chartDataCalls")
        result = extract_chart_data(image_url)
        step["outputSize"] = len(result.get("summary", ""))
        if result["status"] != "success":
            record_counter("chartDataFailures")
        return result


def _extract_html_tables_tool(payload: dict[str, Any]) -> dict[str, Any]:
    html = (payload.get("html") or "").strip()
    if not html:
        raise ToolValidationError("extract_html_tables requires non-empty html.")
    with trace_step("tool_extract_html_tables", input_size=len(html)) as step:
        record_counter("htmlTableCalls")
        result = extract_html_tables(html)
        step["outputSize"] = result.get("tableCount", 0)
        if result["status"] != "success":
            record_counter("htmlTableFailures")
        return result


def _meta_analyze_tool(payload: dict[str, Any]) -> dict[str, Any]:
    studies = payload.get("studies") or []
    if not studies:
        raise ToolValidationError("meta_analyze requires a non-empty studies array.")
    with trace_step("tool_meta_analyze", input_size=len(studies)) as step:
        record_counter("metaAnalyzeCalls")
        result = meta_analyze(studies)
        step["outputSize"] = result.get("studyCount", 0)
        if result["status"] != "success":
            record_counter("metaAnalyzeFailures")
        return result
