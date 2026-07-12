import json
import unittest

import requests

from benchmarks.external_search.provider_benchmark import (
    ARXIV_ENDPOINT,
    CROSSREF_ENDPOINT,
    MAX_RESPONSE_BYTES,
    SEMANTIC_SCHOLAR_ENDPOINT,
    build_benchmark_result,
    fetch_provider_case,
    is_relevant_result,
    run_live_benchmark,
    select_providers,
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
                "publicationVenue": None,
            }
        ]
    }


def _arxiv_atom_response():
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<feed xmlns="http://www.w3.org/2005/Atom"'
        b' xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"'
        b' xmlns:arxiv="http://arxiv.org/schemas/atom">\n'
        b'  <entry>\n'
        b'    <id>http://arxiv.org/abs/1706.03762</id>\n'
        b'    <title>Attention Is All You Need</title>\n'
        b'    <published>2017-06-12T00:00:00Z</published>\n'
        b'    <author><name>Ashish Vaswani</name></author>\n'
        b'    <summary>  The dominant sequence transduction models.  </summary>\n'
        b'    <link rel="related" title="doi" href="https://doi.org/10.48550/arXiv.1706.03762"/>\n'
        b'    <arxiv:license href="https://creativecommons.org/licenses/by/4.0/"/>\n'
        b'  </entry>\n'
        b'</feed>\n'
    )


_MALFORMED_ATOM = b"not-xml-content"


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
        self.assertIn("title", kwargs["params"]["fields"])
        self.assertIn("publicationVenue", kwargs["params"]["fields"])
        self.assertNotIn("x-api-key", kwargs["headers"])
        self.assertEqual(result["results"][0]["license"], "CCBY")

    def test_arxiv_request_is_fixed_and_snapshot_is_sanitized(self):
        response = _Response(
            raw=_arxiv_atom_response(),
            headers={"X-Rate-Limit-Limit": "50", "Authorization": "secret"},
        )
        session = _Session([response])

        result = fetch_provider_case("arxiv", CASE, session=session)

        url, kwargs = session.calls[0]
        self.assertEqual(url, ARXIV_ENDPOINT)
        self.assertEqual(kwargs["params"]["search_query"], CASE["query"])
        self.assertEqual(kwargs["params"]["start"], 0)
        self.assertEqual(kwargs["params"]["max_results"], 5)
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (3.05, 10.0))
        self.assertIn("application/atom+xml", kwargs["headers"]["Accept"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["rateLimitHeaders"], {"x-rate-limit-limit": "50"})
        self.assertNotIn("Authorization", json.dumps(result))
        self.assertNotIn("sequence transduction", json.dumps(result))
        self.assertTrue(result["results"][0]["hasAbstract"])
        self.assertGreater(result["results"][0]["abstractChars"], 0)
        self.assertEqual(result["results"][0]["providerId"], "1706.03762")
        self.assertEqual(result["results"][0]["title"], "Attention Is All You Need")
        self.assertTrue(response.closed)

    def test_arxiv_xml_parse_error_is_handled(self):
        session = _Session([_Response(raw=_MALFORMED_ATOM)])

        result = fetch_provider_case("arxiv", CASE, session=session)

        self.assertEqual(result["status"], "invalid_response")

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
        session = _Session([
            _Response(_crossref_payload()),
            _Response(_semantic_payload()),
            _Response(raw=_arxiv_atom_response()),
        ])
        sleeps = []

        snapshot = run_live_benchmark(
            fixtures,
            session=session,
            sleep_fn=sleeps.append,
        )

        self.assertEqual(len(session.calls), 3)
        self.assertEqual(sleeps, [1.1, 1.1])
        self.assertEqual(snapshot["providers"]["crossref"]["authMode"], "anonymous")
        self.assertEqual(snapshot["providers"]["semantic_scholar"]["authMode"], "anonymous")
        self.assertEqual(snapshot["providers"]["arxiv"]["authMode"], "anonymous")
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
                "arxiv": {
                    "authMode": "anonymous",
                    "requests": [{
                        "caseId": CASE["id"],
                        "status": "success",
                        "durationMs": 500,
                        "results": [{"rank": 1, "title": CASE["expectedTitle"], "doi": CASE["expectedDoi"], "hasAbstract": True}],
                    }],
                },
            }
        }

        result = build_benchmark_result(fixtures, snapshot)
        crossref = result["providers"]["crossref"]
        arxiv = result["providers"]["arxiv"]

        self.assertEqual(crossref["successRate"], 1.0)
        self.assertEqual(crossref["doiCoverage"], 0.5)
        self.assertEqual(crossref["abstractCoverage"], 0.5)
        self.assertEqual(crossref["hitAt5"], 1.0)
        self.assertEqual(crossref["meanReciprocalRank"], 0.5)
        self.assertAlmostEqual(crossref["qualityScore"], 0.675)

        self.assertEqual(arxiv["successRate"], 1.0)
        self.assertEqual(arxiv["hitAt5"], 1.0)
        self.assertAlmostEqual(arxiv["qualityScore"], 1.0)

        self.assertEqual(result["selection"]["status"], "complete")
        self.assertEqual(set(result["selection"]["recommendedCombination"]), {"crossref", "semantic_scholar", "arxiv"})

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
            "arxiv": {"authMode": "anonymous", "requests": healthy_requests},
        }}

        result = build_benchmark_result(fixtures, snapshot)

        self.assertEqual(result["providers"]["crossref"]["failureCounts"]["rateLimited429"], 1)
        self.assertEqual(result["providers"]["crossref"]["failureCounts"]["timeout"], 1)
        self.assertEqual(result["selection"]["status"], "insufficient_data")
        self.assertIsNone(result["selection"]["recommendedCombination"])

    def test_three_provider_selection_with_excluded(self):
        """When one provider is 100% rate-limited and others pass, it is excluded."""
        metrics = {
            "crossref": {
                "authMode": "anonymous",
                "caseCount": 6,
                "successfulCases": 6,
                "qualityScore": 0.60,
                "successRate": 1.0,
                "medianLatencyMs": 500,
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
            "arxiv": {
                "authMode": "anonymous",
                "caseCount": 6,
                "successfulCases": 6,
                "qualityScore": 0.55,
                "successRate": 1.0,
                "medianLatencyMs": 800,
                "failureCounts": {"rateLimited429": 0},
            },
        }

        selection = select_providers(metrics)

        self.assertEqual(selection["status"], "complete")
        self.assertEqual(set(selection["recommendedCombination"]), {"crossref", "arxiv"})
        self.assertIn("semantic_scholar", selection["excludedProviders"])
        self.assertIn("crossref,arxiv", selection["productionConfig"])

    def test_recommended_combination_includes_all_eligible(self):
        """All three providers passing gives all three in the combination."""
        metrics = {
            "crossref": {
                "authMode": "anonymous",
                "caseCount": 6,
                "successfulCases": 6,
                "qualityScore": 0.50,
                "successRate": 1.0,
                "medianLatencyMs": 500,
                "failureCounts": {"rateLimited429": 0},
            },
            "semantic_scholar": {
                "authMode": "anonymous",
                "caseCount": 6,
                "successfulCases": 6,
                "qualityScore": 0.65,
                "successRate": 1.0,
                "medianLatencyMs": 300,
                "failureCounts": {"rateLimited429": 0},
            },
            "arxiv": {
                "authMode": "anonymous",
                "caseCount": 6,
                "successfulCases": 6,
                "qualityScore": 0.60,
                "successRate": 1.0,
                "medianLatencyMs": 700,
                "failureCounts": {"rateLimited429": 0},
            },
        }

        selection = select_providers(metrics)

        self.assertEqual(selection["status"], "complete")
        self.assertEqual(set(selection["recommendedCombination"]), {"crossref", "semantic_scholar", "arxiv"})
        # Ranked by quality score: semantic_scholar(0.65), arxiv(0.60), crossref(0.50)
        self.assertIn("semantic_scholar", selection["productionConfig"])
        self.assertIn("arxiv", selection["productionConfig"])
        self.assertIn("crossref", selection["productionConfig"])

    def test_close_scores_use_success_then_latency_then_operational_burden(self):
        """Quality tiebreakers: success rate → latency → operational burden."""
        metrics = {
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
            "arxiv": {
                "successfulCases": 6,
                "qualityScore": 0.82,
                "successRate": 0.9,
                "medianLatencyMs": 200,
            },
        }

        # semantic_scholar wins on quality (highest among those with 1.0 success rate)
        selection = select_providers(metrics)
        self.assertIn("semantic_scholar", selection["recommendedCombination"])
        # arxiv has same quality but lower success rate, ranked below
        ranking = selection["recommendedCombination"]
        self.assertEqual(ranking[0], "semantic_scholar")

    def test_anonymous_provider_rate_limited_for_every_case_is_operationally_ineligible(self):
        metrics = {
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
            "arxiv": {
                "authMode": "anonymous",
                "caseCount": 6,
                "successfulCases": 6,
                "qualityScore": 0.350,
                "successRate": 1.0,
                "medianLatencyMs": 900,
                "failureCounts": {"rateLimited429": 0},
            },
        }

        selection = select_providers(metrics)

        self.assertEqual(selection["status"], "complete")
        self.assertIn("crossref", selection["recommendedCombination"])
        self.assertIn("arxiv", selection["recommendedCombination"])
        self.assertIn("semantic_scholar", selection["excludedProviders"])
        self.assertIn("429", selection.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
