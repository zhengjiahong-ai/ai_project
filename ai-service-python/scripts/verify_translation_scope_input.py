"""Read recorded page input/cache; check scope handling without any generation."""
import hashlib
import json
import sys

from services.page_translation_service import (_normalize_layout_blocks, _normalize_translated_blocks,
                                               _build_structured_translation_prompt)
from services.translation_math import TOKEN, has_intact_math_tokens, has_unsafe_subtraction_scope

recorded = json.load(sys.stdin)
before_hash = hashlib.sha256(json.dumps(recorded, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
blocks = _normalize_layout_blocks(recorded['layout'])
definition = next(block for block in blocks if 'one subtract' in block['text'])
payload = next(row['response'] for row in recorded['cache']['cacheRows']
               if isinstance(row['response'], dict) and isinstance(row['response'].get('translatedBlocks'), list)
               and any(item['id'] == definition['id'] and '减去' in item['translatedText']
                       for item in row['response']['translatedBlocks']))
bad = next(item for item in payload['translatedBlocks'] if item['id'] == definition['id'])
assert has_intact_math_tokens(definition['text'], bad['translatedText'])
assert has_unsafe_subtraction_scope(definition['text'], bad['translatedText'])
all_translation_blocks = [item for row in recorded['cache']['cacheRows']
                          if isinstance(row['response'], dict)
                          for item in row['response'].get('translatedBlocks', [])]
accepted = _normalize_translated_blocks({'translatedBlocks': all_translation_blocks}, blocks)
assert definition['id'] not in {item['id'] for item in accepted} and accepted
prompt = _build_structured_translation_prompt(3, '', [definition])
assert '"variable": "T"' in prompt and 'Qji' not in prompt
assert not any(item['structureVerified'] for item in definition['mathContext'])
markers = TOKEN.findall(definition['text'])
assert len(markers) == 2
neutral = ('体积见' + markers[0] + '；透射率依据前方各高斯的一减不透明度项计算，累积形式见' + markers[1] + '。')
neutral_result = _normalize_translated_blocks({'translatedBlocks': [{'id': definition['id'], 'translatedText': neutral}]}, [definition])
assert neutral_result and neutral_result[0]['translatedText'] == neutral
after_hash = hashlib.sha256(json.dumps(recorded, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
assert before_hash == after_hash
print(json.dumps({'scope': 'Recorded real page input and cached bad response; neutral fragment is synthetic, not a regenerated translation',
                  'providerCalls': 0, 'taskWrites': 0, 'cacheWrites': 0, 'sourceBlockId': definition['id'],
                  'checks': {'existingBadMarkersIntact': True, 'badSubtractionScopeRejected': True,
                             'otherCachedBlocksPreserved': True, 'variableContextProvided': True,
                             'damagedOperatorNotGuessed': True, 'neutralFragmentKeepsMarkers': True,
                             'recordedInputUnchanged': True},
                  'acceptedCachedBlockIds': [item['id'] for item in accepted],
                  'mathContext': definition['mathContext'], 'beforeHash': before_hash, 'afterHash': after_hash}, ensure_ascii=False))
