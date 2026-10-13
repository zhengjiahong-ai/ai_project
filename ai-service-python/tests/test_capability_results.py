import pytest
from services.capability_result_service import adapt_capability_result


@pytest.mark.parametrize('mode', ['read', 'quiz'])
def test_learning_has_the_same_result_fields_and_question_is_in_short_message(mode):
    result = adapt_capability_result('learning.start', {'paperIds': ['A.pdf'], 'upstream': {'taskId': 'workspace', 'pdfId': 'A.pdf', 'mode': mode}},
        {'status': 'success', 'message': '开始理解', 'question': '解释方法', 'state': {'mode': mode, 'status': 'active', 'pdfId': 'A.pdf'},
         'sources': [{'pdfId': 'a.pdf', 'sourceId': 's', 'text': 'evidence'}]})
    assert result['resultVersion'] == 1 and result['capability'] == mode
    assert result['message'] == '开始理解\n\n解释方法'
    assert result['materialScope']['taskId'] == 'workspace'
    assert result['sources'][0]['pdfId'] == 'A.pdf'
    assert result['artifact'] is None and result['steps'] == []


@pytest.mark.parametrize('capability', ['background', 'critique', 'compare'])
def test_professional_result_keeps_common_fields_and_full_artifact(capability):
    scope = {'taskId': 'workspace', 'allowedPaperIds': ['A.pdf'], 'primaryPaperId': 'A.pdf', 'strictScope': True}
    result = adapt_capability_result('conversation.execute', {'paperIds': ['A.pdf']},
        {'status': 'success', 'capability': capability, 'message': 'short result', 'materialScope': scope, 'sources': [],
         'artifact': {'text': 'full result', 'paperIds': ['A.pdf'], 'sources': []}})
    assert result['resultVersion'] == 1
    assert result['message'] == 'short result' and result['artifact']['text'] == 'full result'
    assert result['materialScope'] == scope


def test_research_plan_uses_workspace_identity_not_native_job_identity():
    result = adapt_capability_result('research.start', {'workspaceTaskId': 'workspace', 'paperIds': ['A.pdf'], 'upstream': {'pdfId': 'A.pdf'}},
        {'status': 'success', 'task': {'taskId': 'research-job', 'status': 'awaiting_plan_review'}})
    assert result['capability'] == 'research'
    assert result['materialScope']['taskId'] == 'workspace'
    assert result['task']['taskId'] == 'research-job'
    assert result['artifact'] is None


def test_long_learning_explanation_is_saved_without_filling_the_dialogue():
    body = '结论。\n\n' + '完整解释。' * 400
    result = adapt_capability_result('learning.action', {'paperIds': ['A.pdf'], 'upstream': {'taskId': 'workspace', 'action': 'remediate'}},
        {'message': body, 'state': {'mode': 'read', 'status': 'paused', 'pdfId': 'A.pdf'}, 'sources': []})
    assert result['capability'] == 'background'
    assert len(result['message']) < 1100
    assert result['artifact']['text'] == body


def test_native_failure_and_outside_evidence_cannot_be_disguised_as_success():
    with pytest.raises(ValueError):
        adapt_capability_result('research.start', {}, {'status': 'error'})
    with pytest.raises(ValueError, match='来源'):
        adapt_capability_result('learning.start', {'paperIds': ['A.pdf'], 'upstream': {'taskId': 'workspace'}},
            {'message': 'answer', 'state': {'pdfId': 'A.pdf'}, 'sources': [{'pdfId': 'outside.pdf'}]})
