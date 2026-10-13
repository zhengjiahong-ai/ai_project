"""Validate reported table measurements against exact cited cells."""
import re

from services.deep_research.table_evidence import visible_table_packet

_VALUE = r'\d+(?:\.\d+)?'
_METRIC = re.compile(rf'(?<![A-Za-z])(FPS|PSNR|SSIM|LPIPS|Size|Mem)\s*[↑↓:=：]?\s*({_VALUE})', re.I)
_UNIT = re.compile(rf'({_VALUE})\s*(FPS|[KMG]i?B|dB)(?![A-Za-z])', re.I)


def _key(text):
    return re.sub(r'\s+', '', text).casefold()


def dataset_label(text):
    """Drop only a generic trailing English descriptor, never a split/variant."""
    return re.sub(r'\s+datasets?\s*$', '', text, flags=re.I).strip() or text


def validate_table_bindings(claim, evidence):
    """Return a rejection reason; semantic checking still follows this gate."""
    text = str(claim.get('text', ''))
    conditions = claim.get('conditions') or {}
    if isinstance(conditions, dict):
        text += ' ' + ' '.join(str(v) for v in conditions.values())
    metric_mentions = {(v, m.upper()) for m, v in _METRIC.findall(text)}
    unit_mentions = {(v, u.upper()) for v, u in _UNIT.findall(text)}
    bindings = claim.get('tableBindings')
    # Location can point to a table caption containing explicit prose. Only
    # cell-derived quotations need column binding; prose still goes through
    # exact-number and semantic checks, even beside an unverified table.
    table_sources = {e['evidenceId']: e for e in evidence
                     if e.get('tableData') or 'Table row ' in e.get('quote', '')
                     or re.search(r'\|[^\n]*\|', e.get('quote', ''))}
    if not table_sources and not bindings:
        return None
    if not metric_mentions and not unit_mentions and not bindings:
        return None
    prose_measurements = set()
    for item in evidence:
        if item['evidenceId'] in table_sources:
            continue
        quote = item.get('quote', '')
        prose_measurements.update((v, m.upper()) for m, v in _METRIC.findall(quote))
        prose_measurements.update((v, u.upper()) for v, u in _UNIT.findall(quote))
    if not isinstance(bindings, list) or not bindings:
        return 'missing_table_bindings' if (metric_mentions | unit_mentions) - prose_measurements else None
    # An anonymous slash-separated series does not expose dataset/value pairing.
    if re.search(r'\d\s*[/／]\s*\d', text):
        return 'ambiguous_table_series'
    supported = set(prose_measurements)
    for binding in bindings:
        if not isinstance(binding, dict):
            return 'invalid_table_binding'
        if not isinstance(binding.get('evidenceId'), str):
            return 'invalid_table_binding'
        source = table_sources.get(binding['evidenceId'])
        if not source:
            return 'table_binding_outside_citation'
        packet = visible_table_packet(source.get('tableData'), source.get('quote', ''))
        group_index, row_number = binding.get('groupIndex'), binding.get('rowNumber')
        if (not packet or type(group_index) is not int or type(row_number) is not int
                or not 0 <= group_index < len(packet['groups'])):
            return 'unverified_table_cell'
        dataset, metrics = packet['groups'][group_index]
        row = next((row for row in packet['rows'] if row[0] == row_number), None)
        metric = binding.get('metric')
        if not row or metric not in metrics:
            return 'unverified_table_cell'
        column = sum(len(g[1]) for g in packet['groups'][:group_index]) + metrics.index(metric)
        value = row[2][column]
        if binding.get('value') != value:
            return 'table_cell_mismatch'
        dataset_visible = any(re.search(r'(?<![a-z0-9])' + re.escape(_key(label)) + r'(?![a-z0-9])', _key(text))
                              for label in (dataset, dataset_label(dataset)))
        if not dataset_visible or any(_key(label) not in _key(text) for label in (row[1], metric, value)):
            return 'table_condition_not_displayed'
        match = re.fullmatch(rf'({_VALUE})([A-Za-z]*)', value)
        if match:
            supported.add((match[1], metric.upper()))
            if match[2]:
                supported.add((match[1], match[2].upper()))
            if metric.upper() == 'PSNR':
                supported.add((match[1], 'DB'))
    if not (metric_mentions | unit_mentions) <= supported:
        return 'unbound_table_measurement'
    return None
