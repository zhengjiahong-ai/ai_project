import json
import unittest

import requests

from benchmarks.external_search.provider_benchmark import (
    CROSSREF_ENDPOINT,
    MAX_RESPONSE_BYTES,
    SEMANTIC_SCHOLAR_ENDPOINT,
    build_benchmark_result,
    fetch_provider_case,
    is_relevant_result,
    run_live_benchmark,
)


CASE = {
    "id": "attention",
    "query": "Attention Is All You Need",
    "expectedTitle": "Attention Is All You Need",
    "expectedDoi": "10.48550/arXiv.1706.03762",
    "titleSimilarityThreshold": 0.75,
}


class _Response:
    def __init__(self, payload=None, status_code=200, headers=None, raw=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._raw = raw if raw is not None else json.dumps(payload or {}).encode("utf-8")
        self.closed = False

    def iter_content(self, chunk_size=65536):
        del chunk_size
        yield self._raw

    def close(self):
        self.closed = True


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _crossref_payload():
    return {
        "message": {
            "items": [
                {
                    "DOI": "10.48550/ARXIV.1706.03762",
                    "title": ["Attention Is All You Need"],
                    "published": {"date-parts": [[2017]]},
                    "URL": "https://doi.org/10.48550/arXiv.1706.03762",
                    "abstract": "<jats:p>Transformer abstract.</jats:p>",
                    "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
                }
            ]
        }
    }


def _semantic_payload():
    return {
        "data": [
            {
                "paperId": "649def34f8be52c8b66281af98ae884c09aef38b",
                "title": "Attention Is All You Need",
                "year": 2017,
                "externalIds": {"DOI": "10.48550/ARXIV.1706.03762"},
                "url": "https://www.semanticscholar.org/paper/649def34",
                "abstract": "Transformer abstract.",
                "openAccessPdf": {"license": "CCBY"},
            }
        ]
    }


class ExternalSearchLiveBenchmarkTests(unittest.TestCase):
    def test_crossref_request_is_fixed_and_snapshot_is_sanitized(self):
        response = _Response(
            _crossref_payload(),
            headers={"X-Rate-Limit-Limit": "50", "Authorization": "secret"},
        )
        session = _Session([response])

        result = fetch_provider_case("crossref", CASE, session=session)

        url, kwargs = session.calls[0]
        self.assertEqual(url, CROSSREF_ENDPOINT)
        self.assertEqual(kwargs["params"], {"query.bibliographic": CASE["query"], "rows": 5})
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (3.05, 10.0))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["rateLimitHeaders"], {"x-rate-limit-limit": "50"})
        self.assertNotIn("Authorization", json.dumps(result))
        self.assertNotIn("Transformer abstract", json.dumps(result))
        self.assertTrue(result["results"][0]["hasAbstract"])
        self.assertGreater(result["results"][0]["abstractChars"], 0)
        self.assertTrue(response.closed)

    def test_semantic_scholar_request_uses_only_metadata_fields_without_authentication(self):
        session = _Session([_Response(_semantic_payload())])

        result = fetch_provider_case("semantic_scholar", CASE, session=session)

        url, kwargs = session.calls[0]
        self.assertEqual(url, SEMANTIC_SCHOLAR_ENDPOINT)
        self.assertEqual(kwargs["params"]["query"], CASE["query"])
        self.assertEqual(kwargs["params"]["limit"], 5)
        self.assertIn("paperId,title,year,abstract,externalIds,url,openAccessPdf", kwargs["params"]["fields"])
        self.assertNotIn("x-api-key", kwargs["headers"])
        self.assertEqual(result["results"][0]["license"], "CCBY")

    def test_response_limit_timeout_and_malformed_json_are_structured_failures(self):
        too_large = _Response(raw=b"x" * (MAX_RESPONSE_BYTES + 1))
        timeout = requests.Timeout("secret timeout details")
        malformed = _Response(raw=b"not-json")
        session = _Session([too_large, timeout, malformed])

        results = [
            fetch_provider_case("crossref", CASE, session=session),
            fetch_provider_case("crossref", CASE, session=session),
            fetch_provider_case("crossref", CASE, session=session),
        ]

        self.assertEqual([item["status"] for item in results], [
            "response_too_large",
            "timeout",
            "invalid_json",
        ])
        self.assertNotIn("secret timeout details", json.dumps(results))

    def test_http_failures_preserve_only_allowlisted_metadata(self):
        session = _Session([
            _Response(
                {"error": "credential rejected"},
                status_code=429,
                headers={"Retry-After": "10", "Set-Cookie": "secret"},
            )
        ])

        result = fetch_provider_case("semantic_scholar", CASE, session=session)

        self.assertEqual(result["status"], "http_error")
        self.assertEqual(result["httpStatus"], 429)
        self.assertEqual(result["rateLimitHeaders"], {"retry-after": "10"})
        self.assertEqual(result["results"], [])
        self.assertNotIn("credential rejected", json.dumps(result))

    def test_live_run_is_sequential_bounded_and_anonymous(self):
        fixtures = {"schemaVersion": "1.0", "cases": [CASE]}
        session = _Session([_Response(_crossref_payload()), _Response(_semantic_payload())])
        sleeps = []

        snapshot = run_live_benchmark(
            fixtures,
            session=session,
            sleep_fn=sleeps.append,
        )

        self.assertEqual(len(session.calls), 2)
        self.assertEqual(sleeps, [1.1])
        self.assertEqual(snapshot["providers"]["crossref"]["authMode"], "anonymous")
        self.assertEqual(snapshot["providers"]["semantic_scholar"]["authMode"], "anonymous")
        self.assertNotIn("x-api-key", session.calls[1][1]["headers"])


class ExternalSearchOfflineBenchmarkTests(unittest.TestCase):
    def test_relevance_accepts_normalized_doi_or_title_jaccard(self):
        self.assertTrue(is_relevant_result(CASE, {
            "doi": "https://doi.org/10.48550/ARXIV.1706.03762",
            "title": "unrelated",
        }))
        self.assertTrue(is_relevant_result(CASE, {
            "doi": "",
            "title": "Attention: Is All You Need!",
        }))
        self.assertFalse(is_relevant_result(CASE, {
            "doi": "10.1000/wrong",
            "title": "Attention mechanisms for images",
        }))

    def test_offline_metrics_and_quality_score_are_deterministic(self):
        fixtures = {"schemaVersion": "1.0", "cases": [CASE]}
        snapshot = {
            "providers": {
                "crossref": {
                    "authMode": "anonymous",
                    "requests": [{
                        "caseId": CASE["id"],
                        "status": "success",
                        "durationMs": 100,
                        "results": [
                            {"rank": 1, "title": "wrong", "doi": "", "hasAbstract": False},
                            {"rank": 2, "title": CASE["expectedTitle"], "doi": CASE["expectedDoi"], "hasAbstract": True},
                        ],
                    }],
                },
                "semantic_scholar": {
                    "authMode": "anonymous",
                    "requests": [{
                        "caseId": CASE["id"],
                        "status": "success",
                        "durationMs": 200,
                        "results": [{"rank": 1, "title": "wrong", "doi": "", "hasAbstract": False}],
                    }],
                },
            }
        }

        result = build_benchmark_result(fixtures, snapshot)
        crossref = result["providers"]["crossref"]

        self.assertEqual(crossref["successRate"], 1.0)
        self.assertEqual(crossref["doiCoverage"], 0.5)
        self.assertEqual(crossref["abstractCoverage"], 0.5)
        self.assertEqual(crossref["hitAt5"], 1.0)
        self.assertEqual(crossref["meanReciprocalRank"], 0.5)
        self.assertEqual(crossref["medianLatencyMs"], 100)
        self.assertEqual(crossref["p95LatencyMs"], 100)
        self.assertAlmostEqual(crossref["qualityScore"], 0.675)
        self.assertEqual(result["selection"]["status"], "insufficient_data")
        self.assertIsNone(result["selection"]["selectedProvider"])

    def test_failure_counters_and_five_of_six_gate_block_selection(self):
        fixtures = {
            "schemaVersion": "1.0",
            "cases": [dict(CASE, id=f"case-{index}") for index in range(6)],
        }
        failure_requests = [
            {"caseId": f"case-{index}", "status": "success", "durationMs": 10, "results": []}
            for index in range(4)
        ] + [
            {"caseId": "case-4", "status": "http_error", "httpStatus": 429, "durationMs": 10, "results": []},
            {"caseId": "case-5", "status": "timeout", "durationMs": 10, "results": []},
        ]
        healthy_requests = [
            {"caseId": f"case-{index}", "status": "success", "durationMs": 20, "results": []}
            for index in range(6)
        ]
        snapshot = {"providers": {
            "crossref": {"authMode": "anonymous", "requests": failure_requests},
            "semantic_scholar": {"authMode": "anonymous", "requests": healthy_requests},
        }}

        result = build_benchmark_result(fixtures, snapshot)

        self.assertEqual(result["providers"]["crossref"]["failureCounts"]["rateLimited429"], 1)
        self.assertEqual(result["providers"]["crossref"]["failureCounts"]["timeout"], 1)
        self.assertEqual(result["selection"]["status"], "insufficient_data")
        self.assertIsNone(result["selection"]["selectedProvider"])

    def test_close_scores_use_success_then_latency_then_operational_burden(self):
        provider_metrics = {
            "crossref": {
                "successfulCases": 6,
                "qualityScore": 0.80,
                "successRate": 1.0,
                "medianLatencyMs": 300,
            },
            "semantic_scholar": {
                "successfulCases": 6,
                "qualityScore": 0.82,
                "successRate": 1.0,
                "medianLatencyMs": 200,
            },
        }

        from benchmarks.external_search.provider_benchmark import select_provider

        self.assertEqual(select_provider(provider_metrics)["selectedProvider"], "semantic_scholar")
        provider_metrics["semantic_scholar"]["medianLatencyMs"] = 300
        self.assertEqual(select_provider(provider_metrics)["selectedProvider"], "crossref")

    def test_anonymous_provider_rate_limited_for_every_case_is_operationally_ineligible(self):
        provider_metrics = {
            "crossref": {
                "authMode": "anonymous",
                "caseCount": 6,
                "successfulCases": 6,
                "qualityScore": 0.399167,
                "successRate": 1.0,
                "medianLatencyMs": 552,
                "failureCounts": {"rateLimited429": 0},
            },
            "semantic_scholar": {
                "authMode": "anonymous",
                "caseCount": 6,
                "successfulCases": 0,
                "qualityScore": 0.0,
                "successRate": 0.0,
                "medianLatencyMs": None,
                "failureCounts": {"rateLimited429": 6},
            },
        }

        from benchmarks.external_search.provider_benchmark import select_provider

        selection = select_provider(provider_metrics)

        self.assertEqual(selection["status"], "complete")
        self.assertEqual(selection["selectedProvider"], "crossref")
        self.assertEqual(selection["excludedProviders"], ["semantic_scholar"])
        self.assertEqual(selection["reason"], "anonymous_access_unavailable")


if __name__ == "__main__":
    unittest.main()
