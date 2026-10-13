"""Diagnose cached v7 responses only; never calls a Provider or publishes a task."""
import json
import sys

from services.grounded_critique import ABSENCE
from services.grounded_numeric_rendering import FREE_NUMBER, MENTION, QUANTITY, TOKEN
from services.page_translation_service import _normalize_layout_blocks
from services.translation_math import has_unsafe_subtraction_scope

recorded = json.load(sys.stdin)
responses = [row['response'] for row in recorded['cache']['cacheRows'] if isinstance(row['response'], dict)]
critique = next(item for item in responses if 'findings' in item)
comparison = next(item for item in responses if 'dimensions' in item)
absence = []
for finding in critique['findings']:
    hit = ABSENCE.search(finding['summary'])
    if hit:
        absence.append({'summary': finding['summary'], 'matchedText': hit.group()})
free = []
for claim in comparison['claims'] + [cell for row in comparison['dimensions'] for cell in row['cells']]:
    if 'numericBindings' not in claim:
        continue
    text = TOKEN.sub('', claim['summary'])
    hits = [match.group() for pattern in (FREE_NUMBER, MENTION, QUANTITY) for match in pattern.finditer(text)]
    if hits:
        free.append({'summary': claim['summary'], 'matches': hits})
blocks = _normalize_layout_blocks(recorded['layout'])
definition = next(item for item in blocks if 'one subtract' in item['text'])
bad_translation = next(item for response in responses for item in response.get('translatedBlocks', [])
                       if item['id'] == definition['id'])
assert absence and free and has_unsafe_subtraction_scope(definition['text'], bad_translation['translatedText'])
print(json.dumps({'scope': 'Cached real v7 response diagnosis; not accepted replay or new generation',
                  'providerCalls': 0, 'taskWrites': 0, 'absenceClaims': absence,
                  'freeNumericMatches': free, 'translationScopeRejected': True,
                  'translationBlock': bad_translation}, ensure_ascii=False))
