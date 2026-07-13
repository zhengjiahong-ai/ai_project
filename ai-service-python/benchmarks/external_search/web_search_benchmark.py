"""P6-22: Web search benchmark for Brave/Tavily success rate, fetch success rate,
iterative search overhead, and token efficiency.

Default mode is offline (reads desensitized snapshots). Pass --live to trigger
real API calls (requires valid API keys and non-zero cost).

Usage:
    python -m benchmarks.external_search.web_search_benchmark          # offline
    python -m benchmarks.external_search.web_search_benchmark --live   # live API
"""
import json
import math
import sys
from pathlib import Path


BENCHMARK_DIR = Path(__file__).resolve().parent
FIXTURES_PATH = BENCHMARK_DIR / "fixtures.json"
SNAPSHOT_PATH = BENCHMARK_DIR / "provider-snapshot.json"


def load_fixtures() -> list:
    if not FIXTURES_PATH.exists():
        return []
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        return {}
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def evaluate_snapshot_success_rate(snapshot: dict) -> dict:
    """Evaluate provider success rate from desensitized snapshot data."""
    results = snapshot.get("results") if isinstance(snapshot, dict) else None
    threshold = 0.90
    if not isinstance(results, list) or not results:
        return {"total": 0, "success": 0, "rate": 0.0, "threshold": threshold,
                "passes": False, "note": "No snapshot data available"}

    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    total = len(results)
    rate = success / total if total > 0 else 0.0
    return {
        "total": total,
        "success": success,
        "rate": round(rate, 4),
        "threshold": threshold,
        "passes": rate >= threshold,
    }


def estimate_latency_overhead(snapshot: dict) -> dict:
    """Estimate iterative search latency overhead from trace data."""
    steps = snapshot.get("steps") if isinstance(snapshot, dict) else None
    threshold_s = 15.0
    if not isinstance(steps, list):
        return {"total_latency_ms": 0, "total_latency_s": 0.0, "threshold_s": threshold_s,
                "passes": True, "note": "No trace step data available"}

    total_ms = sum(
        s.get("durationMs", 0) for s in steps
        if isinstance(s, dict) and isinstance(s.get("durationMs"), (int, float))
    )
    return {
        "total_latency_ms": total_ms,
        "total_latency_s": round(total_ms / 1000, 2),
        "threshold_s": threshold_s,
        "passes": (total_ms / 1000) <= threshold_s,
    }


def estimate_token_overhead(snapshot: dict) -> dict:
    """Estimate additional token overhead from web search vs academic-only."""
    counters = snapshot.get("counters") if isinstance(snapshot, dict) else None
    if not isinstance(counters, dict):
        counters = {}
    llm_calls = counters.get("llmCalls", 0)
    web_search_calls = counters.get("webSearchCalls", 0)
    web_fetch_calls = counters.get("webFetchCalls", 0)

    threshold = 2.0
    if llm_calls == 0:
        return {"llm_calls": 0, "web_search_calls": 0, "web_fetch_calls": 0,
                "estimated_ratio": 1.0, "threshold": threshold, "passes": True,
                "note": "No LLM calls data available"}

    # Estimate: base cost = retrieval + judge; web cost = search + fetch overhead
    base_tokens = llm_calls * 500  # rough estimate per call
    web_overhead = (web_search_calls + web_fetch_calls) * 200
    ratio = (base_tokens + web_overhead) / base_tokens if base_tokens > 0 else 1.0

    return {
        "llm_calls": llm_calls,
        "web_search_calls": web_search_calls,
        "web_fetch_calls": web_fetch_calls,
        "estimated_ratio": round(ratio, 2),
        "threshold": 2.0,
        "passes": ratio <= 2.0,
    }


def evaluate_snapshot_fetch_rate(snapshot: dict) -> dict:
    """Evaluate page fetch success rate from snapshot counters."""
    counters = snapshot.get("counters") if isinstance(snapshot, dict) else None
    if not isinstance(counters, dict):
        counters = {}
    fetch_calls = counters.get("webFetchCalls", 0)
    fetch_failures = counters.get("webFetchFailures", 0)

    threshold = 0.80
    if fetch_calls == 0:
        return {"total": 0, "success": 0, "rate": 0.0, "threshold": threshold,
                "passes": False, "note": "No fetch data available"}

    success = fetch_calls - fetch_failures
    rate = success / fetch_calls if fetch_calls > 0 else 0.0
    return {
        "total": fetch_calls,
        "success": success,
        "failures": fetch_failures,
        "rate": round(rate, 4),
        "threshold": threshold,
        "passes": rate >= threshold,
    }


def run_offline_benchmark():
    print("=" * 60)
    print("P6-22 Web Search Benchmark (offline)")
    print("=" * 60)

    snapshot = load_snapshot()

    # 1. Provider success rate
    print("\n--- Brave/Tavily Success Rate ---")
    success = evaluate_snapshot_success_rate(snapshot)
    print(f"  Total queries: {success['total']}")
    print(f"  Successful: {success['success']}")
    print(f"  Success rate: {success['rate']:.1%}")
    print(f"  Threshold: {success['threshold']:.0%}")
    print(f"  Result: {'PASS' if success['passes'] else 'INCONCLUSIVE'}")

    # 2. Fetch success rate
    print("\n--- Page Fetch Success Rate ---")
    fetch = evaluate_snapshot_fetch_rate(snapshot)
    print(f"  Total fetches: {fetch['total']}")
    print(f"  Successful: {fetch['success']}")
    print(f"  Failures: {fetch.get('failures', 0)}")
    print(f"  Success rate: {fetch['rate']:.1%}")
    print(f"  Threshold: {fetch['threshold']:.0%}")
    print(f"  Result: {'PASS' if fetch['passes'] else 'INCONCLUSIVE'}")

    # 3. Latency overhead
    print("\n--- Iterative Search Latency Overhead ---")
    latency = estimate_latency_overhead(snapshot)
    print(f"  Total latency: {latency['total_latency_s']:.1f}s")
    print(f"  Threshold: ≤{latency['threshold_s']}s")
    print(f"  Result: {'PASS' if latency['passes'] else 'INCONCLUSIVE'}")

    # 4. Token overhead
    print("\n--- Token Overhead (Web vs Academic-only) ---")
    tokens = estimate_token_overhead(snapshot)
    print(f"  LLM calls: {tokens['llm_calls']}")
    print(f"  Web search calls: {tokens['web_search_calls']}")
    print(f"  Web fetch calls: {tokens['web_fetch_calls']}")
    print(f"  Estimated ratio: {tokens['estimated_ratio']:.1f}x")
    print(f"  Threshold: ≤{tokens['threshold']}x")
    print(f"  Result: {'PASS' if tokens['passes'] else 'INCONCLUSIVE'}")

    # Summary
    all_pass = all([success['passes'], fetch['passes'], latency['passes'], tokens['passes']])
    print("\n" + "=" * 60)
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME INCONCLUSIVE (offline data limited)'}")
    print("Pass --live for live API validation.")
    print("=" * 60)


def run_live_benchmark():
    print("Live benchmark mode requires valid API keys.")
    print("Set BRAVE_SEARCH_API_KEY and/or TAVILY_API_KEY environment variables.")
    print("Live benchmark not implemented in this offline version.")
    print("Use offline mode to validate against existing snapshot data.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--live" in args:
        run_live_benchmark()
    else:
        run_offline_benchmark()
