"""Selectable table cells with server-owned identities and literal conditions."""
import hashlib
import json
import re

from services.comparison_measurements import _numeric

# Conservative explicit device/model forms. No hardware is guessed from a
# title, a metadata label, or another paper. Ambiguous papers get no choices.
HARDWARE = re.compile(
    r'\b(?:(?:NVIDIA|AMD|Intel)\s+)?(?:(?:GeForce|Quadro|Tesla|RTX|GTX|Radeon)\s+)*'
    r'(?:[AHVT]\d{2,5}|(?:RTX|GTX|RX)\s*\d{3,5})(?:\s*Ti)?\s+(?:GPU|CPU)\b'
    r'|\b(?:GPU|CPU)\s+[A-Z](?:\d{2,5})?\b', re.I)


def attach_experiment_facts(clean, validation, catalog):
    """Only visible whitelisted cells and visible same-paper conditions qualify."""
    devices = {}
    for source in validation:
        for quote in catalog[source['sourceId']].values():
            for match in HARDWARE.finditer(quote):
                hardware = match.group()
                key = re.sub(r'\b(?:NVIDIA|AMD|Intel|GeForce|Quadro|Tesla)\b', '', hardware, flags=re.I)
                key = ''.join(sorted(re.findall(r'[a-z0-9]+', key.lower())))
                entry = devices.setdefault(source['pdfId'], {}).setdefault(key, {'hardware': hardware, 'references': []})
                if len(hardware) > len(entry['hardware']):
                    entry['hardware'] = hardware
                ref = {'sourceId': source['sourceId'], 'quote': quote}
                if ref not in entry['references']:
                    entry['references'].append(ref)
    visible = {source['sourceId']: source for source in clean}
    for source in validation:
        packet = source.get('_verifiedTable')
        conditions = devices.get(source['pdfId'], {})
        if not packet or len(conditions) != 1:
            continue
        condition = next(iter(conditions.values()))
        facts, choices = {}, []
        for row in packet['rows']:
            literal = f'Table row {row[0]}: ' + ' | '.join([row[1], *row[2]])
            if literal not in catalog[source['sourceId']].values():
                continue
            offset = 0
            for group, (dataset, metrics) in enumerate(packet['groups']):
                for column, metric in enumerate(metrics):
                    try:
                        value = row[2][offset + column]
                        _numeric(value)
                    except (ValueError, IndexError):
                        continue
                    fact = {'sourceId': source['sourceId'], 'pdfId': source['pdfId'],
                            'row': row[0], 'model': row[1], 'group': group, 'metric': metric,
                            'dataset': dataset, 'value': value, 'hardware': condition['hardware'],
                            'references': [{'sourceId': source['sourceId'], 'quote': literal}],
                            'conditionReferences': condition['references']}
                    fact_id = hashlib.sha256(json.dumps(fact, sort_keys=True).encode()).hexdigest()[:20]
                    facts[fact_id] = fact
                    choices.append({'factId': fact_id, **{key: fact[key] for key in
                                    ('model', 'dataset', 'metric', 'value', 'hardware')}})
                offset += len(metrics)
        if facts:
            source['_experimentFacts'] = facts
            visible[source['sourceId']]['experimentFacts'] = choices


def expand_fact_binding(binding, sources):
    """Select identities; never repair conflicting free-form legacy bindings."""
    if set(binding) - {'id', 'kind', 'factId', 'baselineFactId', 'operation', 'decimals'}:
        raise ValueError('实验选项不能同时填写自由行号、条件或数值。')
    facts = {key: fact for source in sources.values() for key, fact in source.get('_experimentFacts', {}).items()}
    fact_id = binding.get('factId')
    fact = facts.get(fact_id) if isinstance(fact_id, str) else None
    if fact is None:
        raise ValueError('实验选项不存在或不属于本次材料。')
    operation = binding.get('operation', 'value')
    baseline_id = binding.get('baselineFactId')
    if operation == 'value':
        if baseline_id is not None:
            raise ValueError('单个实验值不填写比较基线选项。')
        baseline = fact
    else:
        baseline = facts.get(baseline_id) if isinstance(baseline_id, str) else None
        if baseline is None or baseline_id == fact_id:
            raise ValueError('实验计算须选择另一个明确的基线选项。')
        if any(fact[key] != baseline[key] for key in ('sourceId', 'pdfId', 'group', 'metric', 'hardware')):
            raise ValueError('实验选项的数据集、指标、硬件或来源表不一致。')
    expanded = {key: fact[key] for key in ('sourceId', 'row', 'group', 'metric', 'dataset', 'hardware')}
    expanded.update(id=binding['id'], kind='experiment', operation=operation,
                    baselineRow=baseline['row'], baseline=baseline['model'],
                    conditionReferences=fact['conditionReferences'], _factModel=fact['model'])
    if 'decimals' in binding:
        expanded['decimals'] = binding['decimals']
    refs = [*fact['references'], *baseline['references'], *fact['conditionReferences']]
    return expanded, refs
