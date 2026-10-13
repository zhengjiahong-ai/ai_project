from copy import deepcopy
import json
import pytest

from services.deep_research.coverage import validate_plan
from services.deep_research.data_prerequisite import ensure_data_prerequisite, QUERY
from services.deep_research.graph import make_acquire_node, make_plan_node


def plan():
    return [{'itemId': 'only-question', 'question': 'Design an experiment', 'dependencies': [],
             'obligations': [{'obligationId': 'mechanism', 'question': 'How does pruning work?',
                              'requiredSources': ['p'], 'searchQuery': 'pruning'}]}]


def test_adds_one_acquisition_requirement_without_changing_user_question_count():
    original = plan()
    before = deepcopy(original)
    result = ensure_data_prerequisite(original, ['p', 'q', 'p'], 'Design a controlled experiment')
    assert original == before
    assert len(validate_plan(result)) == 1
    assert result[0]['obligations'][1:] == original[0]['obligations']
    assert result[0]['obligations'][0]['requiredSources'] == ['p', 'q']
    assert ensure_data_prerequisite(result, ['p', 'q'], 'Design a controlled experiment') == result


def test_existing_id_or_untrusted_marker_does_not_suppress_prerequisite():
    original = plan()
    original[0]['obligations'][0]['obligationId'] = 'data_availability'
    result = ensure_data_prerequisite(original, ['p'], 'Design a controlled experiment')
    assert result[0]['obligations'][0]['obligationId'] == 'data_availability_1'
    assert len(result[0]['obligations']) == 2


def test_short_question_cannot_create_ungrounded_support_exemption():
    result = ensure_data_prerequisite(plan(), ['p'], '实验')
    assert result[0]['obligations'][0]['purpose'] == 'answer_requirement'


def test_added_requirement_uses_existing_scope_checked_retrieval_and_persists_binding():
    research_plan = ensure_data_prerequisite(plan(), ['p', 'revoked'], 'Design a controlled experiment')
    record = {'state': {'plan': research_plan}, 'materials': [
        {'materialId': 'p'}, {'materialId': 'revoked'}], 'sourcePolicy': {'mode': 'task_only'}}
    calls = []
    def update(run, mutate, **kwargs):
        nonlocal record
        record = mutate(record)
        return deepcopy(record)
    def retrieve(query, pdf, **kwargs):
        calls.append((query, pdf))
        return [{'sourceId': query, 'pdfId': pdf, 'text': 'The dataset has two scenes.',
                 'accessLevel': 'fulltext'}]
    make_acquire_node(retrieve, lambda run, paper: paper == 'p', update)({'run_id': 'r'})
    assert (QUERY, 'p') in calls
    assert not any(paper == 'revoked' for _, paper in calls)
    source = next(s for s in record['state']['sources'] if s['sourceId'] == QUERY)
    assert source['obligationIds'] == [research_plan[0]['obligations'][0]['obligationId']]


@pytest.mark.parametrize('kind,expected', [('experiment_design', 2), ('paper_comparison', 1)])
def test_planner_omission_is_repaired_only_for_experimental_output(kind, expected):
    record = {'question': 'Design a controlled experiment', 'state': {'outputKind': kind},
              'materials': [{'materialId': 'p'}]}
    def update(run, mutate, **kwargs):
        nonlocal record
        record = mutate(record)
        return deepcopy(record)
    make_plan_node(lambda *args: {'content': json.dumps(plan())}, update, validate_plan)({'run_id': 'r'})
    saved = record['state']['plan']
    assert len(saved) == 1
    assert len(saved[0]['obligations']) == expected
    if kind == 'experiment_design':
        assert saved[0]['obligations'][0]['searchQuery'] == QUERY
