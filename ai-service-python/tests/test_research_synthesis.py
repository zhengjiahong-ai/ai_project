import json
from unittest.mock import patch

import pytest

from services.research_synthesis import synthesize_research_finding, validate_claim


BODY = "We maximize radar SINR subject to communication QoS and an active RIS power constraint."
EVIDENCE = [{"sourceId": "paper-a-chunk-3", "pdfId": "a", "text": "Paper: A title\nContent:\n" + BODY}]


def run(claims, limitations=None):
    payload = json.dumps({"claims": claims, "limitations": limitations or []})
    with patch("services.socratic_service._call_guarded_llm", return_value=payload) as model:
        result = synthesize_research_finding("优化目标是什么？", EVIDENCE)
    return result, model.call_args.args[0]


def claim(quote=BODY, sid="paper-a-chunk-3", kind="reported"):
    return {"summary": "最大化雷达SINR，同时约束通信QoS和有源RIS功率。", "kind": kind,
            "references": [{"sourceId": sid, "quote": quote}]}


def test_answers_question_using_body_and_only_actual_citations():
    result, prompt = run([claim()])
    assert "最大化雷达SINR" in result["summary"]
    assert result["sourceIds"] == ["paper-a-chunk-3"]
    assert "Paper: A title" not in prompt
    assert result["claims"][0]["references"][0]["quote"] == BODY


@pytest.mark.parametrize("bad", [claim("A title"), claim("We minimize radar SINR instead."), claim(sid="invented")])
def test_rejects_metadata_invented_quote_and_unknown_source(bad):
    with pytest.raises(ValueError):
        run([bad])


def test_inference_label_and_unknown_are_preserved():
    result, _ = run([claim(kind="inference")], ["当前片段不足以判断全局最优性。"])
    assert result["summary"].startswith("推断：")
    assert "全局最优性" in result["summary"]


def test_irrelevant_evidence_is_not_published_as_proof():
    result, _ = run([], ["当前材料未覆盖这一问题。"])
    assert result["answerStatus"] == "insufficient_evidence"
    assert result["sourceIds"] == []


def test_empty_evidence_does_not_call_provider():
    with patch("services.socratic_service._call_guarded_llm") as model:
        result = synthesize_research_finding("问题", [])
    model.assert_not_called()
    assert result["answerStatus"] == "insufficient_evidence"


def test_metadata_only_source_is_not_body_evidence():
    with patch("services.socratic_service._call_guarded_llm") as model:
        result = synthesize_research_finding("问题", [{"sourceId": "a", "text": "Paper: A title\nSection: Results"}])
    model.assert_not_called()
    assert result["sourceIds"] == []


def test_structured_report_keeps_answer_first_without_fake_cross_validation():
    from services.research_aggregator import build_research_report
    result, _ = run([claim()])
    finding = {**result, "subQuestion": "优化目标是什么？", "sources": EVIDENCE,
               "coverage": {"crossSourceAgreement": 1.0}, "verdict": "CORRECT"}
    with patch("llm.client.get_llm") as model:
        report = build_research_report("研究优化目标", "brief", [], [finding], trace_summary={"counters": {"llmCalls": 5}})
    model.assert_not_called()
    assert "最大化雷达SINR" in report
    assert report.index("最大化雷达SINR") < report.index("<details>")
    assert BODY in report
    assert "已确认" not in report and "JUDGE" not in report and "执行统计" not in report


def test_resumed_mixed_report_does_not_revert_to_heuristic_validation():
    from services.research_aggregator import build_research_report
    result, _ = run([claim()])
    new = {**result, "subQuestion": "优化目标"}
    old = {"summary": "保留的历史结论", "subQuestion": "旧问题", "verdict": "CORRECT", "sources": EVIDENCE}
    with patch("services.evidence_cross_validator.cross_validate_evidence") as validate:
        report = build_research_report("问题", "brief", [], [old, new])
    validate.assert_not_called()
    assert "保留的历史结论" in report and "尚未逐论断核对原文" in report
    assert "最大化雷达SINR" in report and "JUDGE" not in report


def test_verified_long_continuous_quote_is_split_without_losing_evidence():
    body = ("Results show that Gaussian Pruning and Recovery effectively removes redundant Gaussians, "
            "retaining only those crucial for scene representation. SH Distillation reduces the Spherical "
            "Harmonics degree, simplifying the lighting model with minimal quality loss. Furthermore, "
            "Vector Quantization efficiently compresses the feature space, creating a more compact representation.")
    assert len(body) == 372
    checked = validate_claim(claim(body), [{**EVIDENCE[0], 'text': body}])
    parts = [ref['quote'] for ref in checked['references']]
    assert len(parts) > 1
    assert all(8 <= len(part) <= 300 and part in body for part in parts)
    assert ' '.join(parts) == body
    assert all(ref['sourceId'] == EVIDENCE[0]['sourceId'] for ref in checked['references'])


@pytest.mark.parametrize('quote', [
    'Reported observations ' * 20 + 'invented ending',
    'Reported observations ' * 15 + '... final findings',
])
def test_long_quote_with_invented_or_stitched_text_is_still_rejected(quote):
    sources = [{**EVIDENCE[0], 'text': 'Reported observations ' * 30 + ' final findings'}]
    with pytest.raises(ValueError, match='摘录无法在正文中找到'):
        validate_claim(claim(quote), sources)
