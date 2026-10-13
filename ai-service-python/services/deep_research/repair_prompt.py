"""Lossless factoring of repeated coverage questions in repair prompts."""
from copy import deepcopy


def factor_repair_questions(checks):
    questions, identifiers, packed = {}, {}, {}
    for claim_id, check in checks.items():
        row = deepcopy(check)
        missing = row.get('missingQuestions')
        if (isinstance(missing, list) and all(isinstance(q, str) for q in missing)
                and 'missingQuestionIds' not in row):
            ids = []
            for question in missing:
                if question not in identifiers:
                    key = f'Q{len(questions) + 1}'
                    identifiers[question] = key
                    questions[key] = question
                ids.append(identifiers[question])
            del row['missingQuestions']
            row['missingQuestionIds'] = ids
        packed[claim_id] = row
    return questions, packed
