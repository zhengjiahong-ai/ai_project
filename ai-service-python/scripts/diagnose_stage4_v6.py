"""Diagnose saved model payloads only; no retrieval, generation or persistence."""
import json
import sys
from services.comparison_measurements import MENTION, name_key, validate_numeric_comparison

saved = json.load(sys.stdin)
result = []
for row in saved['cacheRows']:
    payload = row['response']
    if not isinstance(payload, dict):
        continue
    claims = payload.get('findings', [])
    claims += [cell for dimension in payload.get('dimensions', []) for cell in dimension['cells']]
    for claim in claims:
        measurements = claim.get('measurements', [])
        if not measurements and not MENTION.search(claim['summary']):
            continue
        record = {'summary': claim['summary'], 'measurementCount': len(measurements),
                  'mentionedValues': [match['value'] or match['score'] for match in MENTION.finditer(claim['summary'])]}
        if measurements:
            record['conditionsNotLiteralInSummary'] = sorted(set(
                str(measurement.get(key)) for measurement in measurements for key in ('dataset', 'hardware', 'baseline')
                if name_key(measurement.get(key)) not in name_key(claim['summary'])))
            record['structuredValues'] = [measurement['value'] for measurement in measurements]
        else:
            try:
                validate_numeric_comparison(claim, {'summary': claim['summary'], 'references': []}, {})
            except ValueError as error:
                record['currentGuardError'] = str(error)
        result.append(record)
print(json.dumps({'scope': 'Raw-response diagnostics, not an accepted replay or a new model case',
                  'claims': result, 'providerCalls': 0, 'taskWrites': 0}, ensure_ascii=False))
