"""Recheck saved v3 comparison quotes against existing indexed text, without models."""
import json
import re
from pathlib import Path

base = Path(__file__).resolve().parent
response = json.loads((base / 'stage4-reading-v3-cached-responses.json').read_text(encoding='utf-8-sig'))['composition']['response']
source_data = json.loads((base / 'stage4-compose-v3-validation-sources.json').read_text(encoding='utf-8-sig'))
sources = {item['sourceId']: item for item in source_data['sources']}
claims = [('claim', item) for item in response.get('claims', [])]
claims += [(dimension['label'], cell) for dimension in response.get('dimensions', []) for cell in dimension['cells']]
rows = []
used = set()
for location, claim in claims:
    for ref in claim.get('references', []):
        sid, quote = ref['sourceId'], ref['quote']
        used.add(sid)
        text = sources.get(sid, {}).get('text', '').split('Content:\n')[-1]
        flatten = lambda value: re.sub(r'\s+', ' ', value).strip()
        rows.append({'location': location, 'sourceId': sid, 'quote': quote,
                     'validLength': 8 <= len(quote.strip()) <= 300,
                     'matchesFullIndexedBody': bool(text) and flatten(quote) in flatten(text),
                     'matchesFirst1400Chars': bool(text) and flatten(quote) in flatten(text[:1400]),
                     'containsEllipsis': '...' in quote or '…' in quote})
report = {'newModelCalls': 0, 'checkedReferences': len(rows),
          'fullBodyMismatches': [row for row in rows if not row['matchesFullIndexedBody'] or not row['validLength']],
          'evidenceBoundary': 'Existing indexed source text; full-body mismatches cannot be explained by prompt truncation alone.'}
(base / 'stage4-compose-v3-quote-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
# Retain only the cited chunks, not full-paper copies, in this diagnostic record.
(base / 'stage4-compose-v3-validation-sources.json').write_text(json.dumps({'sources': [sources[sid] for sid in sorted(used) if sid in sources],
                                                                          'newModelCalls': 0}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'references': len(rows), 'fullBodyMismatches':len(report['fullBodyMismatches']),
                  'ellipticalMismatches':sum(row['containsEllipsis'] for row in report['fullBodyMismatches']), 'newModelCalls':0}))
