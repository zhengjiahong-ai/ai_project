"""Attach one bounded data-feasibility investigation to an experiment plan."""
from copy import deepcopy

QUESTION = ('拟议实验可使用哪些现有数据集或论文子集？核对实际场景/样本名称或数量、'
            '训练与评估划分；沿用其他论文子集时回查该来源，不以整个数据集替代子集。')
QUERY = 'datasets evaluation benchmark subset scenes sample names number train test split'


def ensure_data_prerequisite(plan, source_ids, question):
    """Keep user sub-question count; route acquisition through existing tracked tools.

    This auxiliary investigation is not itself an extra requested answer section.
    Its unresolved gaps still need the ordinary final coverage decision, and any
    chosen data claim separately requires the source-bound availability audit.
    """
    result = deepcopy(plan)
    if not result:
        return result
    sources = list(dict.fromkeys(source_ids))
    excerpt = question[:160]
    expected = {'question': QUESTION, 'searchQuery': QUERY, 'requiredSources': sources,
                'purpose': 'supporting_research' if len(excerpt) >= 8 else 'answer_requirement',
                'requestExcerpt': excerpt}
    obligations = [o for item in result for o in item['obligations']]
    if any(all(o.get(k) == v for k, v in expected.items()) for o in obligations):
        return result
    used = {o['obligationId'] for o in obligations} | {item['itemId'] for item in result}
    identity, suffix = 'data_availability', 0
    while identity in used:
        suffix += 1
        identity = f'data_availability_{suffix}'
    result[0]['obligations'].insert(0, {'obligationId': identity, **expected})
    return result
