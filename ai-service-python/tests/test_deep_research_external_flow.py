import hashlib
from types import SimpleNamespace

import pytest

from services.deep_research.contracts import BudgetExhaustedError, RevisionConflictError, SettlementAlreadyError
from services.deep_research.external import AcademicAcquisition, capabilities, export_saved_source
from services.deep_research.publication import PublicationDispatcher
from services.deep_research.repository import DeepResearchRepository


@pytest.fixture
def repo(tmp_path):
    value = DeepResearchRepository(str(tmp_path / "research.sqlite3"))
    value.initialize()
    value.create_run({"runId": "r", "taskId": "t", "question": "public topic",
                      "sourcePolicy": {"mode": "academic_external"}})
    value.begin_execution("r")
    return value


class AcademicFixture:
    policy = SimpleNamespace(allow_fulltext=True)

    def __init__(self, *, fail=False):
        self.discoveries, self.fetches, self.fail = [], [], fail

    def discover(self, query, limit):
        self.discoveries.append(query)
        key = str(len(self.discoveries))
        return [{"workId": "arxiv:2601.0000" + key, "versionId": "arxiv:2601.0000" + key + "v1",
                 "arxivId": "2601.0000" + key + "v1", "title": "Public work " + key,
                 "url": "https://arxiv.org/abs/2601.0000" + key + "v1",
                 "abstract": "Abstract only reports a proposal.", "accessLevel": "abstract", "contentHash": "a" * 64}]

    def fetch_fulltext(self, arxiv_id):
        self.fetches.append(arxiv_id)
        if self.fail:
            raise OSError("offline")
        return {"accessLevel": "fulltext", "contentHash": "b" * 64, "url": "https://arxiv.org/pdf/" + arxiv_id,
                "pages": [{"page": 4, "text": "The public method reaches 95% accuracy on this fixed benchmark."}]}


def test_external_calls_are_separate_cached_and_literal_metadata_preserved(repo):
    fixture = AcademicFixture()
    acquire = AcademicAcquisition(repo, repo.complete_call, client_factory=lambda record: fixture)
    targets = [{"obligationId": "o", "query": "all:gaussian accuracy"}]
    sources = acquire("r", targets)
    again = acquire("r", targets)
    assert sources == again
    assert len(fixture.discoveries) == len(fixture.fetches) == 1
    assert sources[0]["accessLevel"] == "fulltext" and sources[0]["location"]["page"] == 4
    assert sources[0]["sourceKind"] == "arxiv" and sources[0]["obligationIds"] == ["o"]
    assert sources[0]["url"] == "https://arxiv.org/abs/2601.00001v1"
    assert {call["tool"] for call in repo.list_calls("r")} == {"external_discover", "external_fulltext"}
    budget = repo.require_run("r")["budget"]
    assert budget["externalSearches"] == budget["fulltextFetches"] == 1


def test_unavailable_fulltext_remains_abstract_without_fabricated_page(repo):
    fixture = AcademicFixture(fail=True)
    acquire = AcademicAcquisition(repo, repo.complete_call, client_factory=lambda record: fixture)
    sources = acquire("r", [{"obligationId": "o", "query": "public topic"}])
    assert sources[0]["accessLevel"] == "abstract"
    assert "page" not in sources[0]["location"]
    assert repo.list_calls("r")[-1]["status"] == "failed"
    again = acquire("r", [{"obligationId": "o", "query": "public topic"}])
    assert again == sources and len(fixture.fetches) == 1


def test_one_external_work_can_support_multiple_obligations_without_refetch(repo):
    fixture = AcademicFixture()
    original_discover = fixture.discover
    fixture.discover = lambda query, limit: original_discover("same public topic", limit) if not fixture.discoveries else [{
        "workId": "arxiv:2601.00001", "versionId": "arxiv:2601.00001v1", "arxivId": "2601.00001v1"}]
    acquire = AcademicAcquisition(repo, repo.complete_call, client_factory=lambda record: fixture)
    sources = acquire("r", [{"obligationId": "o1", "query": "topic one"}, {"obligationId": "o2", "query": "topic two"}])
    assert sources and all(source["obligationIds"] == ["o1", "o2"] for source in sources)
    assert len(fixture.fetches) == 1


def test_repeated_work_selects_pages_for_each_question_not_discovery_identity(repo):
    fixture = AcademicFixture()
    original_discover = fixture.discover
    fixture.discover = lambda query, limit: original_discover(query, limit) if not fixture.discoveries else [{
        'workId': 'arxiv:2601.00001', 'versionId': 'arxiv:2601.00001v1', 'arxivId': '2601.00001v1'}]
    original_fetch = fixture.fetch_fulltext
    def fetch(identity):
        result = original_fetch(identity)
        return {**result, 'pages': [{'page': i + 1, 'text': 'encoder features ' * 4}
                                  for i in range(3)] + [
                                      {'page': 4, 'text': 'decoder deformation output ' * 4}]}
    fixture.fetch_fulltext = fetch
    acquire = AcademicAcquisition(repo, repo.complete_call, client_factory=lambda _: fixture)
    sources = acquire('r', [
        {'obligationId': 'encoder', 'query': '2310.08528v3', 'question': 'encoder features'},
        {'obligationId': 'decoder', 'query': '2310.08528v3', 'question': 'decoder deformation output'}])
    decoder = next(s for s in sources if s['location']['page'] == 4)
    assert decoder['obligationIds'] == ['decoder']
    assert 'decoder deformation output' in decoder['text']
    assert len({s['sourceId'] for s in sources}) == len(sources)
    assert len(fixture.fetches) == 1


def test_page_ranking_does_not_reward_repeated_bibliography_identifiers():
    from services.deep_research.external import _select_pages
    pages = [{'page': 9, 'text': 'arXiv preprint Gaussian. ' * 40},
             {'page': 2, 'text': 'encoder ' * 50},
             {'page': 4, 'text': 'The encoder represents temporal features for the deformation decoder.'}]
    ranked = _select_pages(pages, 'arXiv:2310.08528v3 encoder decoder temporal deformation')
    assert ranked[0]['page'] == 4
    assert ranked[-1]['page'] == 9
    assert ranked[0]['text'] == pages[2]['text']


def test_identifier_in_chinese_question_keeps_translated_discovery_terms(repo):
    fixture = AcademicFixture()
    original_fetch = fixture.fetch_fulltext
    def fetch(identity):
        result = original_fetch(identity)
        return {**result, 'pages': [{'page': i + 7, 'text': 'arXiv preprint. ' * 30} for i in range(3)] + [
            {'page': 4, 'text': 'The deformation decoder maps temporal features to Gaussian offsets.'}]}
    fixture.fetch_fulltext = fetch
    acquire = AcademicAcquisition(repo, repo.complete_call, client_factory=lambda _: fixture)
    sources = acquire('r', [{'obligationId': 'decoder', 'query': 'arXiv:2310.08528v3 deformation decoder',
                            'question': 'arXiv:2310.08528v3的解码器负责什么？'}])
    assert sources[0]['location']['page'] == 4
    assert sources[0]['obligationIds'] == ['decoder']
    assert len(fixture.fetches) == 1


@pytest.mark.parametrize("key", ["maxExternalSearches", "maxFulltextFetches"])
def test_client_cannot_widen_network_budget(repo, key):
    record, _ = repo.create_run({"runId": key, "taskId": "t", "budget": {key: 1000}})
    assert record["budget"][key] == 6
    with pytest.raises(ValueError):
        repo.create_run({"runId": key + "-zero", "taskId": "t", "budget": {key: 0}})


def test_report_keeps_conditions_and_labels_in_summary_and_folds_evidence():
    from services.deep_research.reporting import conversation_summary, render_report
    claims = [{"claimId": "p", "kind": "proposal", "text": "固定四组对照", "evidenceRefs": ["e"],
               "conditions": {"数据": "同一训练测试划分"}},
              {"claimId": "long", "kind": "reported", "text": "x" * 600}]
    summary = conversation_summary(claims, "partial")
    assert "实验建议：" in summary and "同一训练测试划分" in summary and "结果尚不完整" in summary
    assert "xxx" not in summary
    body = render_report({"claims": claims[:1], "evidence": [{"evidenceId": "e", "quote": "original quote"}]})
    assert "<details>\n<summary>原文依据</summary>\n" in body
    assert "[1](#research-evidence-e)" in body


def test_short_summary_keeps_three_components_after_scope_statement():
    from services.deep_research.reporting import conversation_summary
    claims = [{'claimId': str(i), 'kind': 'reported', 'text': text}
              for i, text in enumerate(['仅取得摘要。', '第一部分：剪枝。', '第二部分：蒸馏。', '第三部分：量化。'])]
    result = conversation_summary(claims, 'complete')
    assert all(claim['text'] in result for claim in claims)
    assert len(result) <= 500


def test_task_only_policy_never_constructs_external_client(repo):
    repo.update_run("r", lambda r: {**r, "sourcePolicy": {"mode": "task_only"}})
    acquire = AcademicAcquisition(repo, repo.complete_call, client_factory=lambda record: pytest.fail("no external client"))
    assert acquire("r", [{"obligationId": "o", "query": "public"}]) == []
    assert not repo.list_calls("r")


def test_malformed_report_is_failure_and_cannot_publish_inconclusive_result(repo):
    from services.deep_research.graph import make_synthesize_node, make_verify_node, make_publish_node
    from unittest.mock import Mock
    invoke = Mock(return_value={"content": "", "usage": {"output_tokens": 4000}})
    state = {"run_id": "r", "execution_epoch": 1}
    state.update(make_synthesize_node(invoke, repo.update_run)(state))
    assert state["error_code"] == "invalid_synthesis_response"
    verify, publish = Mock(), Mock()
    assert make_verify_node(verify, None, repo.update_run)(state) == {}
    assert make_publish_node(publish, repo.update_run)(state) == {}
    verify.assert_not_called()
    publish.assert_not_called()
    assert not repo.require_run("r").get("publication", {}).get("published")


@pytest.mark.parametrize("counter,limit", [("externalSearches", 6), ("fulltextFetches", 6)])
def test_network_limits_are_atomic_reservations(repo, counter, limit):
    for index in range(limit):
        repo.reserve_call(run_id="r", node="acquire", tool=counter, args_digest=str(index), budget_delta={counter: 1})
    with pytest.raises(BudgetExhaustedError):
        repo.reserve_call(run_id="r", node="acquire", tool=counter, args_digest="excess", budget_delta={counter: 1})
    assert repo.require_run("r")["budget"][counter] == limit


def test_zero_delta_settlement_cannot_replace_known_result(repo):
    call, _ = repo.reserve_call(run_id="r", node="acquire", tool="read", args_digest="zero", budget_delta={})
    repo.complete_call(call["callId"], status="succeeded", result={"stable": True})
    with pytest.raises(SettlementAlreadyError):
        repo.complete_call(call["callId"], status="failed", result={"stable": False})
    assert repo.list_calls("r")[0]["result"] == {"stable": True}
    with pytest.raises(SettlementAlreadyError):
        repo.complete_call(call["callId"], status="failed", result={"stable": False}, allow_late=True)
    assert repo.list_calls("r")[0]["result"] == {"stable": True}


def test_plan_edit_replaces_stale_query_and_cannot_expand_materials(repo):
    from services.deep_research.facade import ResearchFacade
    from services.deep_research.contracts import DeepResearchError
    plan = [{"itemId": "p", "question": "original", "searchQuery": "old topic", "obligations": [
        {"obligationId": "o", "question": "original", "searchQuery": "old topic", "requiredSources": ["paper"]}]}]
    repo.update_run("r", lambda r: {**r, "materials": [{"materialId": "paper"}], "state": {"plan": plan}})
    paused = repo.transition("r", "paused")
    facade = ResearchFacade(repo, lambda **kwargs: None, scope_validator=lambda *args: True)
    edited = [{**plan[0], "question": "new goal", "obligations": [{**plan[0]["obligations"][0], "question": "new goal"}]}]
    result = facade._action_plan("r", paused["runRevision"], {"plan": edited})
    assert result["planRevision"] == 1
    assert "searchQuery" not in result["plan"][0]
    assert "searchQuery" not in result["plan"][0]["obligations"][0]
    edited[0]["obligations"][0]["requiredSources"] = ["foreign"]
    with pytest.raises(DeepResearchError, match="材料范围"):
        facade._action_plan("r", result["runRevision"], {"plan": edited})
    facade.shutdown()


def test_resume_revision_is_checked_inside_execution_transaction(repo):
    paused = repo.transition("r", "paused")
    repo.update_run("r", lambda r: {**r, "stage": "updated"})
    with pytest.raises(RevisionConflictError):
        repo.begin_execution("r", expected_revision=paused["runRevision"])
    assert repo.require_run("r")["status"] == "paused"


def test_export_uses_saved_hash_and_never_fetches(repo, tmp_path, monkeypatch):
    body = b"%PDF-offline-existing-file"
    content_hash = hashlib.sha256(body).hexdigest()
    monkeypatch.setenv("DEEP_RESEARCH_SOURCE_DIR", str(tmp_path))
    (tmp_path / (content_hash + ".pdf")).write_bytes(body)
    source = {"sourceId": "s", "sourceKind": "arxiv", "workId": "arxiv:2601.00001",
              "arxivId": "2601.00001v1", "versionId": "arxiv:2601.00001v1", "contentHash": content_hash,
              "accessLevel": "fulltext", "title": "Existing paper"}
    repo.update_run("r", lambda r: {**r, "state": {"sources": [source]}})
    assert export_saved_source(repo, "r", "s")["pdfBase64"]
    (tmp_path / (content_hash + ".pdf")).write_bytes(b"changed")
    assert "pdfBase64" not in export_saved_source(repo, "r", "s")
    assert not repo.list_calls("r")


def test_outbox_delivery_replays_saved_publication_and_requires_matching_ack(repo):
    repo.publish_report(run_id="r", dedup_key="v1", payload={"reportVersionId": "v1"},
                        report_text="verified report", outcome="complete")
    requests = []
    def post(url, **kwargs):
        requests.append(url)
        version = "wrong" if len(requests) == 1 else "v1"
        return SimpleNamespace(status_code=200, json=lambda: {"status": "success", "runId": "r", "reportVersionId": version})
    publisher = PublicationDispatcher(repo, origin="http://127.0.0.1:8080/api", post=post)
    assert publisher.deliver_once() == 0
    assert publisher.deliver_once() == 1
    assert publisher.deliver_once() == 0
    assert len(requests) == 2 and not repo.list_calls("r")
    assert repo.require_run("r")["state"]["reportVersionId"] == "v1"


def test_capability_flags_do_not_silently_enable_external(monkeypatch):
    for key in ("DEEP_RESEARCH_V2_ENABLED", "DEEP_RESEARCH_EXTERNAL_ENABLED", "DEEP_RESEARCH_FULLTEXT_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    assert capabilities()["externalAcademic"] is False
    monkeypatch.setenv("DEEP_RESEARCH_V2_ENABLED", "true")
    assert capabilities()["externalAcademic"] is False
    monkeypatch.setenv("DEEP_RESEARCH_EXTERNAL_ENABLED", "true")
    assert capabilities()["externalAcademic"] is True and capabilities()["fulltext"] is False
