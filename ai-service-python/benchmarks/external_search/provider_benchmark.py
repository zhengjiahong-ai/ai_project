"""Controlled live sampling and deterministic offline scoring for P3-04 / P6-04.

This benchmark is intentionally isolated from the production Provider factory.
Request destinations and queries cannot be supplied through CLI options.
"""

import argparse
import json
import math
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

import requests


CROSSREF_ENDPOINT = "https://api.crossref.org/works"
SEMANTIC_SCHOLAR_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
PROVIDERS = ("crossref", "semantic_scholar", "arxiv")
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_TIMEOUT = (3.05, 10.0)
REQUEST_INTERVAL_SECONDS = 1.1
RESULT_LIMIT = 5
USER_AGENT = "PixiuExternalSearchBenchmark/0.2 (+offline-provider-evaluation)"
SEMANTIC_SCHOLAR_FIELDS = (
    "paperId,title,year,abstract,externalIds,url,openAccessPdf,publicationVenue"
)
RATE_LIMIT_HEADERS = {
    "retry-after",
    "x-concurrency-limit",
    "x-rate-limit-interval",
    "x-rate-limit-limit",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
}
_ARXIV_NS_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS_ARXIV = "{http://arxiv.org/schemas/atom}"


class BenchmarkResponseTooLarge(ValueError):
    pass


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_string(value):
    return str(value).strip() if value is not None else ""


def normalize_doi(value):
    doi = unquote(_clean_string(value)).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):].strip()
            break
    return doi


def _title_tokens(value):
    return set(re.findall(r"[a-z0-9]+", _clean_string(value).lower()))


def is_relevant_result(case, result):
    expected_doi = normalize_doi(case.get("expectedDoi"))
    result_doi = normalize_doi(result.get("doi"))
    if expected_doi and result_doi == expected_doi:
        return True

    expected_tokens = _title_tokens(case.get("expectedTitle"))
    result_tokens = _title_tokens(result.get("title"))
    if not expected_tokens or not result_tokens:
        return False
    similarity = len(expected_tokens & result_tokens) / len(expected_tokens | result_tokens)
    return similarity >= float(case.get("titleSimilarityThreshold", 0.75))


def _rate_limit_headers(headers):
    return {
        str(key).lower(): _clean_string(value)
        for key, value in headers.items()
        if str(key).lower() in RATE_LIMIT_HEADERS
    }


def _read_json_response(response):
    content_length = response.headers.get("Content-Length") or response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise BenchmarkResponseTooLarge("response exceeded configured limit")
        except ValueError as exc:
            if isinstance(exc, BenchmarkResponseTooLarge):
                raise

    chunks = []
    size = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise BenchmarkResponseTooLarge("response exceeded configured limit")
        chunks.append(chunk)
    payload = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("response root must be an object")
    return payload, size


def _read_xml_response(response):
    """Read ArXiv Atom XML response with size limit."""
    content_length = response.headers.get("Content-Length") or response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise BenchmarkResponseTooLarge("response exceeded configured limit")
        except ValueError as exc:
            if isinstance(exc, BenchmarkResponseTooLarge):
                raise

    chunks = []
    size = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise BenchmarkResponseTooLarge("response exceeded configured limit")
        chunks.append(chunk)
    raw_bytes = b"".join(chunks)
    try:
        root = ElementTree.fromstring(raw_bytes.decode("utf-8"))
    except (ElementTree.ParseError, UnicodeDecodeError) as exc:
        raise ValueError("invalid XML response") from exc
    return root, size


def _crossref_year(item):
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                pass
    return None


def _summarize_crossref(payload):
    items = (payload.get("message") or {}).get("items") or []
    results = []
    for rank, item in enumerate(items[:RESULT_LIMIT], start=1):
        titles = item.get("title") or []
        abstract = _clean_string(item.get("abstract"))
        licenses = item.get("license") or []
        license_value = _clean_string(licenses[0].get("URL")) if licenses else ""
        results.append({
            "rank": rank,
            "providerId": _clean_string(item.get("DOI")),
            "title": _clean_string(titles[0] if titles else ""),
            "year": _crossref_year(item),
            "doi": normalize_doi(item.get("DOI")),
            "url": _clean_string(item.get("URL")),
            "hasAbstract": bool(abstract),
            "abstractChars": len(abstract),
            "license": license_value,
        })
    return results


def _summarize_semantic_scholar(payload):
    results = []
    for rank, item in enumerate((payload.get("data") or [])[:RESULT_LIMIT], start=1):
        abstract = _clean_string(item.get("abstract"))
        external_ids = item.get("externalIds") or {}
        open_access = item.get("openAccessPdf") or {}
        try:
            year = int(item["year"]) if item.get("year") is not None else None
        except (TypeError, ValueError):
            year = None
        results.append({
            "rank": rank,
            "providerId": _clean_string(item.get("paperId")),
            "title": _clean_string(item.get("title")),
            "year": year,
            "doi": normalize_doi(external_ids.get("DOI")),
            "url": _clean_string(item.get("url")),
            "hasAbstract": bool(abstract),
            "abstractChars": len(abstract),
            "license": _clean_string(open_access.get("license")),
        })
    return results


def _summarize_arxiv(root):
    """Parse ArXiv Atom XML and extract top results."""
    entries = root.findall(f"{_ARXIV_NS_ATOM}entry")
    results = []
    for rank, entry in enumerate(entries[:RESULT_LIMIT], start=1):
        arxiv_id = _extract_arxiv_id(entry)
        if not arxiv_id:
            continue

        title = _clean_string(_child_text(entry, f"{_ARXIV_NS_ATOM}title"))
        if not title:
            continue

        year = _extract_arxiv_year(entry)
        abstract = _clean_string(_child_text(entry, f"{_ARXIV_NS_ATOM}summary"))
        doi = _extract_arxiv_doi(entry)
        license_url = _extract_arxiv_license(entry)

        results.append({
            "rank": len(results) + 1,
            "providerId": arxiv_id,
            "title": title,
            "year": year,
            "doi": normalize_doi(doi),
            "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
            "hasAbstract": bool(abstract),
            "abstractChars": len(abstract),
            "license": license_url,
        })
    return results


def _extract_arxiv_id(entry):
    raw = _clean_string(_child_text(entry, f"{_ARXIV_NS_ATOM}id"))
    if not raw:
        return ""
    m = re.search(r"arxiv[:.]org/abs/([a-zA-Z0-9./-]+)", raw)
    if m:
        return m.group(1)
    m = re.match(r"^([a-zA-Z0-9./-]+)$", raw)
    if m:
        return m.group(1)
    return ""


def _extract_arxiv_year(entry):
    published = _clean_string(_child_text(entry, f"{_ARXIV_NS_ATOM}published"))
    match = re.match(r"(\d{4})", published)
    if match:
        try:
            year = int(match.group(1))
            if 1000 <= year <= 9999:
                return year
        except (TypeError, ValueError):
            pass
    return None


def _extract_arxiv_doi(entry):
    for link in entry.findall(f"{_ARXIV_NS_ATOM}link"):
        rel = link.get("rel", "")
        title_attr = (link.get("title") or "").lower()
        href = (link.get("href") or "").strip()
        if rel == "related" and "doi" in title_attr:
            return href
    return ""


def _extract_arxiv_license(entry):
    license_elem = entry.find(f"{_ARXIV_NS_ARXIV}license")
    if license_elem is not None:
        href = (license_elem.get("href") or "").strip()
        if href:
            return href
    return ""


def _child_text(elem, tag):
    child = elem.find(tag)
    if child is not None:
        return "".join(child.itertext())
    return ""


def _request_spec(provider, case):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if provider == "crossref":
        return CROSSREF_ENDPOINT, {
            "query.bibliographic": case["query"],
            "rows": RESULT_LIMIT,
        }, headers
    if provider == "semantic_scholar":
        return SEMANTIC_SCHOLAR_ENDPOINT, {
            "query": case["query"],
            "limit": RESULT_LIMIT,
            "fields": SEMANTIC_SCHOLAR_FIELDS,
        }, headers
    if provider == "arxiv":
        return ARXIV_ENDPOINT, {
            "search_query": case["query"],
            "start": 0,
            "max_results": RESULT_LIMIT,
        }, {"User-Agent": USER_AGENT, "Accept": "application/atom+xml"}
    raise ValueError("unsupported benchmark provider")


def fetch_provider_case(provider, case, session=None, clock=time.perf_counter):
    session = session or requests.Session()
    endpoint, params, headers = _request_spec(provider, case)
    started = clock()
    response = None
    base = {
        "caseId": case["id"],
        "status": "network_error",
        "httpStatus": None,
        "durationMs": 0,
        "responseBytes": 0,
        "rateLimitHeaders": {},
        "results": [],
    }
    try:
        response = session.get(
            endpoint,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
            stream=True,
        )
        base["httpStatus"] = int(response.status_code)
        base["rateLimitHeaders"] = _rate_limit_headers(response.headers)
        if not 200 <= response.status_code < 300:
            base["status"] = "http_error"
            return base
        if provider == "arxiv":
            root, size = _read_xml_response(response)
            base["responseBytes"] = size
            base["results"] = _summarize_arxiv(root)
        else:
            payload, size = _read_json_response(response)
            base["responseBytes"] = size
            base["results"] = (
                _summarize_crossref(payload)
                if provider == "crossref"
                else _summarize_semantic_scholar(payload)
            )
        base["status"] = "success"
        return base
    except requests.Timeout:
        base["status"] = "timeout"
        return base
    except BenchmarkResponseTooLarge:
        base["status"] = "response_too_large"
        return base
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        base["status"] = "invalid_json" if provider != "arxiv" else "invalid_response"
        return base
    except ElementTree.ParseError:
        base["status"] = "invalid_response"
        return base
    except requests.RequestException:
        base["status"] = "network_error"
        return base
    finally:
        base["durationMs"] = round((clock() - started) * 1000)
        if response is not None:
            response.close()


def run_live_benchmark(fixtures, session=None, sleep_fn=time.sleep):
    cases = fixtures.get("cases") or []
    if len(cases) > 12:
        raise ValueError("live benchmark is limited to twelve fixed cases")
    session = session or requests.Session()
    requests_to_make = [(provider, case) for provider in PROVIDERS for case in cases]
    if len(requests_to_make) > 36:
        raise ValueError("live benchmark is limited to thirty-six requests")

    snapshot = {
        "schemaVersion": "1.1",
        "generatedAt": _utc_now(),
        "fixtureSchemaVersion": fixtures.get("schemaVersion", ""),
        "providers": {
            "crossref": {"authMode": "anonymous", "requests": []},
            "semantic_scholar": {"authMode": "anonymous", "requests": []},
            "arxiv": {"authMode": "anonymous", "requests": []},
        },
    }
    for index, (provider, case) in enumerate(requests_to_make):
        snapshot["providers"][provider]["requests"].append(
            fetch_provider_case(
                provider,
                case,
                session=session,
            )
        )
        if index < len(requests_to_make) - 1:
            sleep_fn(REQUEST_INTERVAL_SECONDS)
    return snapshot


def _nearest_rank_percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _score_provider(cases, provider_snapshot):
    requests_by_case = {
        item.get("caseId"): item
        for item in provider_snapshot.get("requests", [])
    }
    successful_cases = 0
    relevant_cases = 0
    reciprocal_rank_sum = 0.0
    result_count = 0
    doi_count = 0
    abstract_count = 0
    latencies = []
    failures = {
        "rateLimited429": 0,
        "server5xx": 0,
        "timeout": 0,
        "authentication": 0,
        "invalidResponse": 0,
    }

    for case in cases:
        request = requests_by_case.get(case["id"], {})
        status = request.get("status")
        http_status = request.get("httpStatus")
        if status == "success":
            successful_cases += 1
            if isinstance(request.get("durationMs"), (int, float)):
                latencies.append(request["durationMs"])
            results = request.get("results") or []
            result_count += len(results)
            doi_count += sum(bool(normalize_doi(item.get("doi"))) for item in results)
            abstract_count += sum(bool(item.get("hasAbstract")) for item in results)
            for result in results[:RESULT_LIMIT]:
                if is_relevant_result(case, result):
                    relevant_cases += 1
                    reciprocal_rank_sum += 1 / int(result.get("rank") or 1)
                    break
        else:
            if http_status == 429:
                failures["rateLimited429"] += 1
            if isinstance(http_status, int) and 500 <= http_status <= 599:
                failures["server5xx"] += 1
            if status == "timeout":
                failures["timeout"] += 1
            if http_status in (401, 403):
                failures["authentication"] += 1
            if status in ("invalid_json", "response_too_large", "invalid_response"):
                failures["invalidResponse"] += 1

    case_count = len(cases)
    success_rate = successful_cases / case_count if case_count else 0.0
    doi_coverage = doi_count / result_count if result_count else 0.0
    abstract_coverage = abstract_count / result_count if result_count else 0.0
    hit_at_5 = relevant_cases / case_count if case_count else 0.0
    mrr = reciprocal_rank_sum / case_count if case_count else 0.0
    quality = 0.35 * hit_at_5 + 0.25 * mrr + 0.20 * abstract_coverage + 0.20 * doi_coverage
    return {
        "authMode": provider_snapshot.get("authMode", "anonymous"),
        "caseCount": case_count,
        "successfulCases": successful_cases,
        "successRate": round(success_rate, 6),
        "doiCoverage": round(doi_coverage, 6),
        "abstractCoverage": round(abstract_coverage, 6),
        "hitAt5": round(hit_at_5, 6),
        "meanReciprocalRank": round(mrr, 6),
        "medianLatencyMs": round(statistics.median(latencies)) if latencies else None,
        "p95LatencyMs": round(_nearest_rank_percentile(latencies, 0.95)) if latencies else None,
        "failureCounts": failures,
        "qualityScore": round(quality, 6),
    }


def select_providers(provider_metrics):
    """Select provider combination based on benchmark metrics.

    Returns a dict with:
    - status: 'complete' | 'insufficient_data'
    - recommendedCombination: list of provider names to use together (or None)
    - excludedProviders: list of providers excluded from recommendation
    - productionConfig: recommended PIXIU_EXTERNAL_SEARCH_PROVIDERS value
    - reason: human-readable explanation
    """
    excluded = []
    eligible = []
    incomplete = []

    for name in PROVIDERS:
        metrics = provider_metrics.get(name, {})
        if not isinstance(metrics, dict):
            continue
        case_count = metrics.get("caseCount", 0)
        success_count = metrics.get("successfulCases", 0)
        # Infer case_count from failure + success counts if not explicitly provided
        if case_count == 0:
            failure_total = sum((metrics.get("failureCounts") or {}).values())
            case_count = success_count + failure_total
        if case_count == 0:
            continue
        gate = max(1, math.ceil(case_count * 0.8))
        if metrics.get("successfulCases", 0) >= gate:
            eligible.append(name)
            continue
        rate_limited = (metrics.get("failureCounts") or {}).get("rateLimited429", 0)
        if (
            metrics.get("authMode") == "anonymous"
            and case_count > 0
            and metrics.get("successfulCases", 0) == 0
            and rate_limited == case_count
        ):
            excluded.append(name)
        else:
            incomplete.append(name)

    if not eligible or incomplete:
        # Determine case count for error message — use the most common case count
        case_counts = [m.get("caseCount", 0) for m in provider_metrics.values() if isinstance(m, dict)]
        default_count = max(case_counts) if case_counts else 6
        return {
            "status": "insufficient_data",
            "recommendedCombination": None,
            "excludedProviders": excluded,
            "productionConfig": None,
            "reason": f"Each usable anonymous provider must successfully complete at least "
                      f"{max(1, math.ceil(default_count * 0.8))} "
                      f"of {default_count} cases.",
        }

    if len(eligible) == 1:
        return {
            "status": "complete",
            "recommendedCombination": eligible,
            "excludedProviders": excluded,
            "productionConfig": eligible[0],
            "reason": "only_one_eligible" if not excluded else "anonymous_access_unavailable",
        }

    # Rank eligible providers by quality score (descending)
    eligible_sorted = sorted(eligible, key=lambda n: provider_metrics[n]["qualityScore"], reverse=True)

    # Check for excluded providers that need API keys
    reason_parts = []
    if excluded:
        reason_parts.append(f"{','.join(excluded)} excluded: anonymous 429 rate-limiting (needs API key)")

    production_config = ",".join(eligible_sorted)

    return {
        "status": "complete",
        "recommendedCombination": eligible_sorted,
        "excludedProviders": excluded,
        "productionConfig": production_config,
        "reason": "; ".join(reason_parts) if reason_parts else "all_eligible_providers_pass_gate",
    }


def build_benchmark_result(fixtures, snapshot):
    cases = fixtures.get("cases") or []
    metrics = {
        provider: _score_provider(cases, (snapshot.get("providers") or {}).get(provider, {}))
        for provider in PROVIDERS
    }
    return {
        "schemaVersion": "1.1",
        "generatedAt": snapshot.get("generatedAt", ""),
        "fixtureSchemaVersion": fixtures.get("schemaVersion", ""),
        "qualityFormula": "0.35*hitAt5 + 0.25*meanReciprocalRank + 0.20*abstractCoverage + 0.20*doiCoverage",
        "providers": metrics,
        "selection": select_providers(metrics),
    }


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="P6-04 external academic Provider benchmark (3 providers, 12 queries)")
    parser.add_argument("--live", action="store_true", help="run the fixed controlled live sample")
    parser.add_argument("--fixture", type=Path, default=directory / "fixtures.json")
    parser.add_argument("--snapshot", type=Path, default=directory / "provider-snapshot.json")
    parser.add_argument("--output", type=Path, default=directory / "benchmark-results.json")
    args = parser.parse_args(argv)

    fixtures = _load_json(args.fixture)
    if args.live:
        snapshot = run_live_benchmark(fixtures)
        _write_json(args.snapshot, snapshot)
    else:
        snapshot = _load_json(args.snapshot)
    result = build_benchmark_result(fixtures, snapshot)
    _write_json(args.output, result)
    selection = result["selection"]
    print(json.dumps(selection, ensure_ascii=False))
    return 0 if selection["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
