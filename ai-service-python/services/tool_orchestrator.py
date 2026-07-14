"""Tool composition orchestrator — plans and executes multi-tool pipelines.

The LLM generates a directed acyclic graph (DAG) of tool calls from a goal
description. The orchestrator then executes the DAG in topological order,
feeding outputs of upstream tools as inputs to downstream tools.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any

from services.trace_service import record_counter, trace_step

LLM_TIMEOUT_S = 25
PIPELINE_TIMEOUT_S = 120


# ── Public API ───────────────────────────────────────────────────────────────

def execute_tool_pipeline(goal: str) -> dict[str, Any]:
    """Plan and execute a multi-tool pipeline for *goal*.

    Returns ``{status, goal, steps, results, error}``.
    """
    if not goal or not goal.strip():
        return _error("Goal cannot be empty.")

    goal = goal.strip()[:500]
    available = _list_available_tools()

    # Step 1: Plan
    plan = _plan_pipeline(goal, available)
    if not plan:
        return _error("Failed to generate tool pipeline plan.")

    # Step 2: Execute
    results: list[dict[str, Any]] = []
    ctx: dict[str, Any] = {"goal": goal}

    deadline = time.monotonic() + PIPELINE_TIMEOUT_S
    for step in plan:
        if time.monotonic() >= deadline:
            results.append({"step": step.get("step", "?"), "status": "timeout", "error": "Pipeline timeout"})
            break
        step_result = _execute_step(step, ctx)
        results.append(step_result)
        if step_result.get("output") is not None:
            ctx[step.get("id", "unknown")] = step_result["output"]

    return {
        "status": "success",
        "goal": goal,
        "plan": plan,
        "results": results,
        "stepCount": len(results),
        "error": "",
    }


# ── Pipeline planning ────────────────────────────────────────────────────────

def _plan_pipeline(goal: str, available: list[dict[str, str]]) -> list[dict[str, Any]]:
    try:
        from llm.client import get_llm

        tool_list = "\n".join(
            f"- {t['name']}: {t['description'][:120]} (inputs: {t['inputs']})"
            for t in available
        )
        prompt = (
            f"目标：{goal}\n\n"
            f"可用工具：\n{tool_list}\n\n"
            "请设计一个工具调用流水线来完成目标。每个步骤需指定：\n"
            "- step: 步骤序号\n"
            "- tool: 工具名称\n"
            "- inputs: 输入参数（可引用前序步骤输出，用 $step_N 表示）\n"
            "- reason: 为什么需要这一步\n\n"
            "用 JSON 数组回复：[{\"step\": 1, \"tool\": \"...\", \"inputs\": {...}, \"reason\": \"...\"}]"
        )

        def _call():
            return get_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            raw = future.result(timeout=LLM_TIMEOUT_S)
    except Exception:
        return _simple_plan(goal, available)

    try:
        text = raw.strip().split("```json")[-1].split("```")[0].strip()
        plan = json.loads(text)
        if isinstance(plan, list) and plan:
            return [
                {
                    "id": f"step_{s.get('step', i+1)}",
                    "tool": str(s.get("tool", "")).strip(),
                    "inputs": s.get("inputs", {}),
                    "reason": str(s.get("reason", ""))[:200],
                }
                for i, s in enumerate(plan) if s.get("tool")
            ]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return _simple_plan(goal, available)


def _simple_plan(goal: str, available: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Rule-based fallback: search → fetch pattern."""
    plan = []
    has_search = any("search" in t["name"] for t in available)
    has_fetch = any("fetch" in t["name"] for t in available)

    if has_search:
        plan.append({
            "id": "step_1", "tool": "search_web",
            "inputs": {"query": goal[:200]},
            "reason": "Search for relevant sources",
        })
    if has_fetch:
        plan.append({
            "id": "step_2", "tool": "fetch_web_page",
            "inputs": {"url": "$step_1.items[0].url" if has_search else goal},
            "reason": "Fetch and extract page content",
        })
    return plan


# ── Step execution ───────────────────────────────────────────────────────────

def _execute_step(step: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    tool_name = step.get("tool", "")
    inputs = dict(step.get("inputs") or {})
    # Resolve $step_N references in inputs
    resolved = {}
    for key, val in inputs.items():
        if isinstance(val, str) and val.startswith("$"):
            resolved[key] = _resolve_ref(val, ctx)
        else:
            resolved[key] = val

    try:
        from services.tool_registry import get_tool_registry
        registry = get_tool_registry()
        with trace_step(f"tool_orchestrator_{tool_name}", input_size=len(str(resolved))) as ts:
            result = registry.invoke(tool_name, resolved)
            ts["outputSize"] = len(str(result))
            return {
                "step": step.get("id", "?"),
                "tool": tool_name,
                "status": "success",
                "output": result,
                "error": "",
            }
    except Exception as exc:
        return {
            "step": step.get("id", "?"),
            "tool": tool_name,
            "status": "error",
            "output": None,
            "error": str(exc)[:200],
        }


def _resolve_ref(ref: str, ctx: dict[str, Any]) -> Any:
    """Resolve ``$step_N.field.subfield`` references from context."""
    path = ref.lstrip("$").split(".")
    value = ctx.get(path[0])
    for segment in path[1:]:
        if isinstance(value, dict):
            value = value.get(segment)
        elif isinstance(value, list):
            try:
                idx = int(segment)
                value = value[idx] if 0 <= idx < len(value) else None
            except (ValueError, IndexError):
                value = None
        else:
            return ref  # can't traverse
    return value if value is not None else ref


def _list_available_tools() -> list[dict[str, str]]:
    try:
        from services.tool_registry import get_tool_registry
        registry = get_tool_registry()
        return [
            {
                "name": t["name"],
                "description": t["description"][:150],
                "inputs": ", ".join(t["inputSchema"].get("required", [])),
            }
            for t in registry.list_tools()
        ]
    except Exception:
        return []


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "goal": "", "plan": [], "results": [], "stepCount": 0, "error": message}
