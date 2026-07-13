"""Iterative agentic search loop: search → fetch → judge → repeat.

Supports multi-round web search with automatic page fetching and
evidence re-evaluation. Terminates on verdict, coverage stall,
max iterations, budget exhaustion, or cancellation.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from services.trace_service import record_counter, trace_step

_MAX_ITERATIONS_DEFAULT = 3
_MAX_URLS_PER_ROUND = 3
_MAX_URLS_TOTAL = 10

_TRUST_ORDER = {"high": 0, "medium": 1, "low": 2, "unknown": 3}


def _env_max_iterations() -> int:
    val = os.environ.get("PIXIU_AGENTIC_MAX_ITERATIONS", "")
    try:
        parsed = int(val)
        if parsed >= 1:
            return parsed
    except (ValueError, TypeError):
        pass
    return _MAX_ITERATIONS_DEFAULT


def run_agentic_search_loop(
    question: str,
    sub_question: str,
    missing_aspects: list,
    query_plan: Dict[str, Any],
    *,
    max_iterations: int | None = None,
    should_cancel: Callable[[], bool] | None = None,
    invoke_search=None,
    invoke_fetch=None,
    invoke_judge=None,
    fetch_cache=None,
    on_progress=None,
) -> Dict[str, Any]:
    """Run iterative search→fetch→judge loop.

    Each round: build queries → search_web → select top URLs → fetch_web_page → judge.
    Terminates on: CORRECT+confident, coverage stall, max iterations, cancel signal.

    Args:
        question: The main research question.
        sub_question: Current sub-question being investigated.
        missing_aspects: Aspects still missing from evidence.
        query_plan: Query plan dict with keywords etc.
        max_iterations: Max loop rounds (default from env or 3).
        should_cancel: Optional cancel signal callback.
        invoke_search: Callable(query, limit) → dict (injectable for tests).
        invoke_fetch: Callable(url, max_chars) → dict (injectable for tests).
        invoke_judge: Callable(question, evidence) → dict (injectable for tests).
        fetch_cache: Optional cache object with get(url)→dict|None (injectable
                     for tests). Cached URLs are skipped during selection.
        on_progress: Optional callback(iteration, pages_fetched, confidence) → None,
                     called after each iteration completes (injectable for tests).

    Returns:
        {iterations, verdict, confidence, evidence_items, web_search_used, pages_fetched}
    """
    from services.external_query_planner import build_web_search_queries

    if max_iterations is None:
        max_iterations = _env_max_iterations()

    if not missing_aspects:
        return {
            "iterations": 0, "verdict": "INCORRECT", "confidence": 0.0,
            "evidence_items": [], "web_search_used": False, "pages_fetched": 0,
        }

    if invoke_search is None:
        invoke_search = _default_invoke_search
    if invoke_fetch is None:
        invoke_fetch = _default_invoke_fetch
    if invoke_judge is None:
        invoke_judge = _default_invoke_judge

    all_evidence: list = []
    all_web_items: list = []
    total_pages_fetched = 0
    fetched_urls: set = set()
    prev_coverage_score = -1.0
    stall_count = 0
    verdict = "INCORRECT"
    confidence = 0.0
    iteration = 0
    judge_suggested_queries: list = []

    while iteration < max_iterations:
        if should_cancel and should_cancel():
            break

        # Step 1: Generate web search queries.
        # Priority: judge's suggestedQueries > LLM refinement > deterministic build.
        if judge_suggested_queries:
            queries = judge_suggested_queries[:3]
            judge_suggested_queries = []
        elif all_web_items:
            from services.external_query_planner import refine_search_queries

            queries = refine_search_queries(
                research_question=question,
                previous_results=all_web_items[-10:],
                missing_aspects=missing_aspects,
            )
            record_counter("queryRefinementCalls")
        else:
            queries = build_web_search_queries(
                research_question=question,
                missing_aspects=missing_aspects,
            )
        if not queries:
            break

        # Steps 2-4: search → select → fetch (per-iteration trace step)
        with trace_step(
            f"agentic_loop_iter_{iteration + 1}",
            input_size=len(queries),
            meta={"iteration": iteration + 1, "queryCount": len(queries)},
        ) as iter_step:
            # Step 2: Execute web search for each query
            web_items = []
            for query in queries:
                try:
                    search_result = invoke_search(query, limit=4)
                except Exception:
                    continue
                if search_result.get("status") == "success":
                    items = search_result.get("items") or []
                    web_items.extend(items)
            if not web_items:
                iter_step["outputSize"] = 0
                break

            all_web_items.extend(web_items)

            # Step 3: Build skip set from session history + cache
            skip_urls = set(fetched_urls)

            if fetch_cache is not None:
                for item in web_items:
                    url = str(item.get("url") or "").strip()
                    if not url or url in skip_urls:
                        continue
                    try:
                        if fetch_cache.get(url) is not None:
                            skip_urls.add(url)
                    except Exception:
                        pass  # cache failure must not crash the loop

            # Select top URLs to fetch (trust-based priority)
            urls_to_fetch = _select_top_urls(
                web_items, missing_aspects=missing_aspects, max_urls=_MAX_URLS_PER_ROUND,
                skip_urls=skip_urls,
            )
            remaining = _MAX_URLS_TOTAL - total_pages_fetched
            urls_to_fetch = urls_to_fetch[:max(0, remaining)]

            # Step 4: Fetch selected pages
            fetched_texts = []
            for item in urls_to_fetch:
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                try:
                    fetch_result = invoke_fetch(url, max_chars=8000)
                except Exception:
                    continue
                if fetch_result.get("status") == "success":
                    content = fetch_result.get("content", "")
                    if content:
                        fetched_texts.append({
                            "sourceId": f"web-page-{iteration + 1}-{len(fetched_texts) + 1}",
                            "sourceType": "web_page",
                            "title": item.get("title", ""),
                            "text": content[:3000],
                            "url": url,
                            "provenance": {
                                "discoveryPath": "web_search→web_page",
                                "searchQuery": str(item.get("query", "")),
                                "searchIteration": iteration + 1,
                                "sourceUrl": url,
                                "retrievalTimestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                            },
                        })
                        total_pages_fetched += 1
                        fetched_urls.add(url)

            iter_step["outputSize"] = len(fetched_texts)
            iter_step["meta"] = {
                **iter_step.get("meta", {}),
                "pagesFetched": len(fetched_texts),
                "totalPagesFetched": total_pages_fetched,
            }

        all_evidence.extend(fetched_texts)

        # Count this as a completed iteration
        iteration += 1
        record_counter("agenticLoopIterations")

        # Notify progress callback if provided
        if on_progress is not None:
            try:
                on_progress(iteration, total_pages_fetched, confidence)
            except Exception:
                pass  # callback failure must not crash the loop

        # Step 5: Re-judge evidence coverage
        evidence_for_judge = all_evidence[-12:] if all_evidence else []
        try:
            judge_result = invoke_judge(sub_question, evidence_for_judge)
        except Exception:
            break

        verdict = str(judge_result.get("verdict") or "INCORRECT")
        confidence = float(judge_result.get("confidence") or 0)
        coverage = judge_result.get("coverage") or {}
        coverage_score = float(coverage.get("score") or 0)
        missing_aspects = list(judge_result.get("missingAspects") or [])

        # Extract judge's suggested queries for next iteration (if any)
        suggested_raw = judge_result.get("suggestedQueries")
        if isinstance(suggested_raw, list) and suggested_raw:
            judge_suggested_queries = [str(q).strip()[:200] for q in suggested_raw if str(q).strip()][:3]

        # Step 6: Check termination conditions
        if verdict == "CORRECT" and confidence >= 0.75:
            break

        if coverage_score <= prev_coverage_score:
            stall_count += 1
        else:
            stall_count = 0
            prev_coverage_score = coverage_score

        if stall_count >= 2:
            break

    return {
        "iterations": iteration,
        "verdict": verdict,
        "confidence": confidence,
        "evidence_items": all_evidence,
        "web_search_used": len(all_web_items) > 0,
        "pages_fetched": total_pages_fetched,
    }


def _select_top_urls(
    web_items: list,
    *,
    missing_aspects: list | None = None,
    max_urls: int = _MAX_URLS_PER_ROUND,
    skip_urls: set[str] | None = None,
) -> list:
    """Select the best URLs to fetch from web search results.

    Priority (rule-based, no LLM):
    1. URL trust tier (high > medium > low > unknown)
    2. Title keyword overlap with missing_aspects
    3. Description length (longer = more informative)

    Args:
        skip_urls: Optional set of URLs to exclude from selection (e.g. already
                   fetched or cached). Defaults to empty set when None.
    """
    from services.content_safety import _classify_url_trust

    missing = missing_aspects or []
    missing_keywords: set[str] = set()
    for aspect in missing:
        for word in aspect.lower().split():
            if len(word) > 2:
                missing_keywords.add(word)

    scored = []
    seen_urls = set(skip_urls or set())
    for item in web_items:
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        trust = _classify_url_trust(url)
        trust_rank = _TRUST_ORDER.get(trust, 3)

        title = str(item.get("title") or "").lower()
        overlap = sum(1 for kw in missing_keywords if kw in title) if missing_keywords else 0

        desc_len = len(str(item.get("description") or item.get("abstract") or ""))

        # Composite score: trust (most important), then relevance, then depth
        score = (trust_rank * -1000) + (overlap * 100) + min(desc_len // 10, 99)
        scored.append({"score": score, "item": item, "url": url})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return [s["item"] for s in scored[:max_urls]]


def _default_invoke_search(query: str, limit: int = 4) -> Dict[str, Any]:
    from services.tool_registry import get_tool_registry

    return get_tool_registry().invoke("search_web", {"query": query, "limit": limit})


def _default_invoke_fetch(url: str, max_chars: int = 8000) -> Dict[str, Any]:
    from services.tool_registry import get_tool_registry

    return get_tool_registry().invoke("fetch_web_page", {"url": url, "maxChars": max_chars})


def _default_invoke_judge(question: str, evidence_items: list) -> Dict[str, Any]:
    from services.tool_registry import get_tool_registry

    return get_tool_registry().invoke("judge_evidence", {
        "question": question,
        "evidenceItems": evidence_items,
    })
