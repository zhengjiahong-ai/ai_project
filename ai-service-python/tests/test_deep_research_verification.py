import pytest

from services.deep_research.verification import make_evidence, verify_claims
from services.deep_research.coverage import coverage_gaps, validate_plan


def source(level="fulltext"):
    return {"workId": "paper", "versionId": "v1", "contentHash": "hash", "accessLevel": level}


def evidence(level="fulltext"):
    return make_evidence(source(level), "15x reduction at 200 FPS", "Result: 15x reduction at 200 FPS.",
                         location={"page": 4}, obligation_ids=["o1"])


def claim(ev, text="15x reduction at 200 FPS", **kw):
    return {"claimId": "c1", "kind": "reported", "text": text, "evidenceRefs": [ev["evidenceId"]], **kw}


def passed(claims, _):
    return [{"claimId": item["claimId"], "status": "passed"} for item in claims]


def test_whitespace_only_quote_normalization():
    ev = make_evidence(source(), "15x\n reduction", "15x   reduction", location={}, obligation_ids=[])
    assert ev["verification"]["literal"] == "passed"
    with pytest.raises(ValueError):
        make_evidence(source(), "150x reduction", "15x reduction", location={}, obligation_ids=[])


def test_number_mismatch_cannot_be_overridden_by_model():
    ev = evidence()
    result = verify_claims([claim(ev, "150x reduction")], [ev], passed)
    assert not result["accepted"]
    assert result["rejected"][0]["reason"] == "numeric_mismatch"


def test_chinese_numbers_and_conditions_are_checked_before_model_verdict():
    ev = evidence()
    assert verify_claims([claim(ev, '速度为999 FPS')], [ev], passed)['rejected'][0]['reason'] == 'numeric_mismatch'
    assert verify_claims([claim(ev, '速度为200 FPS', conditions={'压缩率': '999x'})], [ev], passed)['rejected'][0]['reason'] == 'numeric_mismatch'
    assert verify_claims([claim(ev, '速度为200 FPS')], [ev], passed)['accepted']


def test_positive_sign_in_combined_conditions_preserves_numeric_identity():
    quote = 'At 66% pruning and 2 SH degrees, SSIM goes from 0.927 to 0.926.'
    ev = make_evidence(source(), quote, quote, location={}, obligation_ids=[])
    item = claim(ev, 'SSIM为0.926', conditions={'context': '66%剪枝+2阶SH'})
    assert verify_claims([item], [ev], passed)['accepted']
    for condition in ('66%剪枝+3阶SH', '66%剪枝-2阶SH'):
        wrong = {**item, 'conditions': {'context': condition}}
        assert verify_claims([wrong], [ev], passed)['rejected'][0]['reason'] == 'numeric_mismatch'
    # Matching numbers are insufficient without an independent semantic verdict.
    assert not verify_claims([item], [ev])['accepted']


def test_dimensional_method_name_is_not_a_measured_result():
    ev = make_evidence(source(), 'real-time (≥ 30 fps) at 1080p',
                       'We achieve real-time (≥ 30 fps) at 1080p.', location={}, obligation_ids=[])
    assert verify_claims([claim(ev, '3DGS在1080p达到≥30fps')], [ev], passed)['accepted']
    assert verify_claims([claim(ev, '3D-GS在1080p达到≥30fps')], [ev], passed)['accepted']
    assert not verify_claims([claim(ev, '3DGS达到300fps')], [ev], passed)['accepted']
    assert not verify_claims([claim(ev, '3DGS占用3MB')], [ev], passed)['accepted']


def test_evidence_preserves_original_context_without_promoting_it_to_quote():
    original = 'Supplementary experiment, synthetic scenes. We reach 200 FPS.'
    ev = make_evidence(source(), 'We reach 200 FPS.', original, location={}, obligation_ids=[])
    assert ev['sourceContext'] == original
    assert ev['quote'] == 'We reach 200 FPS.'


def test_selected_evidence_cannot_establish_absence_in_the_whole_paper():
    ev = evidence()
    result = verify_claims([claim(ev, '论文未给出具体数值')], [ev], passed)
    assert result['rejected'][0]['reason'] == 'absence_not_established'
    result = verify_claims([claim(ev, '当前取得片段没有报告动态场景结果', kind='inference')], [ev], passed)
    assert result['accepted']


@pytest.mark.parametrize('text', ['论文未提供动态场景验证', '论文没有涉及跨硬件评测', 'The paper does not report dynamic results',
                               '摘要中未包含实验数据', '摘要不包括实验数据', 'The abstract does not contain measurements'])
def test_other_definitive_absence_wording_requires_explicit_negative_evidence(text):
    ev = evidence()
    assert verify_claims([claim(ev, text, kind='inference')], [ev], passed)['rejected'][0]['reason'] == 'absence_not_established'


def test_abstract_cannot_establish_detailed_experimental_fact():
    ev = evidence("abstract")
    assert not verify_claims([claim(ev)], [ev], passed)["accepted"]
    assert verify_claims([claim(ev, detailLevel="abstract")], [ev], passed)["accepted"]


def test_linked_arxiv_identity_is_not_mistaken_for_a_measured_number():
    ev = {**evidence('abstract'), 'sourceWorkId': 'arxiv:2311.17245'}
    assert verify_claims([claim(ev, 'arXiv:2311.17245报告200 FPS', detailLevel='abstract')], [ev], passed)['accepted']
    assert not verify_claims([claim(ev, 'arXiv:2311.17245报告999 FPS', detailLevel='abstract')], [ev], passed)['accepted']


def test_semantic_check_is_required_and_duplicate_verdict_fails_closed():
    ev = evidence()
    assert not verify_claims([claim(ev)], [ev])["accepted"]
    assert not verify_claims([claim(ev)], [ev], lambda c, e: passed(c, e) * 2)["accepted"]
    assert verify_claims([claim(ev)], [ev], passed)["accepted"]


def test_unknown_source_and_duplicate_claim_are_not_published():
    ev = evidence()
    invalid = {**claim(ev), "evidenceRefs": ["foreign"]}
    assert not verify_claims([invalid], [ev], passed)["accepted"]
    assert len(verify_claims([claim(ev), claim(ev)], [ev], passed)["rejected"]) == 1


def test_inference_requires_premises_proposal_is_separate():
    inferred = {"claimId": "i", "kind": "inference", "text": "may reduce bandwidth", "evidenceRefs": []}
    proposed = {"claimId": "p", "kind": "suggestion", "text": "Try 4 control groups", "evidenceRefs": []}
    result = verify_claims([inferred, proposed], [], passed)
    assert result["accepted"] == [{**proposed, "verification": "proposal"}]


def plan():
    return [{"itemId": "p1", "question": "compare", "obligations": [{"obligationId": "o1", "question": "mechanism"}]}]


def test_each_paper_retains_its_own_coverage_obligation():
    coverage = [{"obligationId": "o1", "sourceWorkId": "A", "state": "supported", "checked": True}]
    assert [g["sourceWorkId"] for g in coverage_gaps(plan(), coverage, ["A", "B"])] == ["B"]


def test_search_miss_is_unresolved_not_contradiction():
    coverage = [{"obligationId": "o1", "sourceWorkId": "A", "state": "unresolved", "checked": True}]
    assert coverage_gaps(plan(), coverage, ["A"])[0]["checked"]


def test_plan_rejects_cycles_and_missing_dependencies():
    assert validate_plan(plan())
    for dependency in ["p1", "absent"]:
        malformed = plan()
        malformed[0]["dependencies"] = [dependency]
        with pytest.raises(ValueError):
            validate_plan(malformed)
