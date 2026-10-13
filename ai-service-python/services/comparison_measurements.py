"""Bind reported comparison numbers to checked cells and local conditions."""
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from services.research_synthesis import evidence_body, validate_claim

NUMBER = r'-?\d+(?:\.\d+)?'
UNIT = (r'frames?\s*(?:/\s*s(?:ec(?:ond)?s?)?|per\s+second)'
        r'|帧\s*(?:[/／]\s*(?:秒|s)|每\s*秒)'
        r'|FPS|KiB|MiB|GiB|KB|MB|GB|dB|PSNR|SSIM|LPIPS|倍|%|％|[x×](?!\s*\d)')
MENTION = re.compile(rf'(?P<value>{NUMBER})\s*\+?\s*(?P<unit>{UNIT})(?![A-Za-z])'
                     # A method identifier such as 3D-GS is not a metric value.
                     # Disallow partial decimal backtracking (27 from 27.13D).
                     rf'|(?P<metric>PSNR|SSIM|LPIPS)\D{{0,8}}?(?P<score>{NUMBER})'
                     rf'(?![A-Za-z0-9]|\.\d)', re.I)


def _mention_unit(mention):
    unit = re.sub(r'\s+', '', mention['unit'] or mention['metric']).lower()
    if unit.startswith(('frame', '帧')) or unit == 'fps':
        return 'FPS'
    if unit in ('x', '×', '倍'):
        return '倍'
    if unit == '％':
        return '%'
    # Binary storage units deliberately remain different from MB/GB.
    return unit.upper()


def name_key(value):
    value = re.sub(r'\[\d+\]', '', str(value)).replace('∗', '*').lower()
    value = value.replace('&', ' and ')
    value = re.sub(r'\bdatasets?\b', '', value)
    return re.sub(r'[\s\-_:：()（）]+', '', value)


def _hardware_display_mentions(summary, hardware):
    if name_key(hardware) in name_key(summary):
        return True
    # Only shorten an identifiable model, never a generic label like GPU A.
    # This affects display matching, not the same-paper literal source check.
    model = re.sub(r'\b(?:NVIDIA|AMD|Intel|GPU|CPU)\b', '', hardware, flags=re.I)
    tokens = re.findall(r'[A-Za-z0-9]+', model)
    if not tokens or not re.search(r'[a-z]\d', ''.join(tokens), re.I):
        return False
    pattern = r'(?<![A-Za-z0-9])' + r'[\s-]*'.join(re.escape(token) for token in tokens) + r'(?![A-Za-z0-9])'
    expected_vendor = re.search(r'\b(NVIDIA|AMD|Intel)\b', hardware, re.I)
    expected_device = re.search(r'\b(GPU|CPU)\b', hardware, re.I)
    for match in re.finditer(pattern, summary, re.I):
        prefix = summary[max(0, match.start() - 24):match.start()]
        suffix = summary[match.end():match.end() + 12]
        vendor = re.search(r'\b(NVIDIA|AMD|Intel)(?:\s+(?:GPU|CPU))*\s*$', prefix, re.I)
        device = re.search(r'\b(GPU|CPU)(?:\s+(?:NVIDIA|AMD|Intel))*\s*$', prefix, re.I) or re.match(r'\s*(GPU|CPU)\b', suffix, re.I)
        if vendor and expected_vendor and vendor[1].lower() != expected_vendor[1].lower():
            continue
        if device and expected_device and device[1].lower() != expected_device[1].lower():
            continue
        return True
    return False


def verified_packet(source, body):
    raw = (source.get('metadata') or {}).get('table_verified_data')
    if not isinstance(raw, str) or len(raw) > 40000:
        return None
    try:
        packet = json.loads(raw)
        visible = [row for row in packet['rows']
                   if 'Table row ' + str(row[0]) + ': ' + ' | '.join([row[1], *row[2]]) in body]
        return {'groups': packet['groups'], 'rows': visible} if visible else None
    except (ValueError, KeyError, TypeError, IndexError):
        return None


def bounded_table_body(source, body, budget):
    """Verified labels count against the SAME evidence character budget."""
    packet = verified_packet(source, body)
    if not packet:
        return body, None
    # Keep at most two complete rows; the selected original chunk remains the
    # evidence. Prefer the proposed method and its adjacent baseline.
    rows = packet['rows']
    proposed = next((i for i, row in enumerate(rows) if re.search(r'\b(?:ours|proposed)\b', row[1], re.I)), len(rows) - 1)
    packet['rows'] = rows[max(0, proposed - 1):proposed + 1]
    reserved = len(json.dumps(packet, ensure_ascii=False, separators=(',', ':')))
    remaining = max(0, budget - reserved)
    if len(body) > remaining:
        first = body.find(f"Table row {packet['rows'][0][0]}: ")
        last_line = f"Table row {packet['rows'][-1][0]}: " + ' | '.join([packet['rows'][-1][1], *packet['rows'][-1][2]])
        end = body.find(last_line) + len(last_line)
        if end - first > remaining or first < 0:
            return body, None
        start = max(0, end - remaining)
        body = body[start:end]
    return body, packet


def _numeric(value):
    match = re.fullmatch(rf'({NUMBER})\s*([A-Za-z%]*)', str(value))
    if not match:
        raise ValueError('比较数字不是可核对的指标值。')
    return Decimal(match[1]), match[2].upper()


def ratio_rounding_distorts(exact, rounded):
    """Bound rounding error to 1%, and preserve whether a ratio differs from one."""
    return ((exact != 0 and abs(rounded - exact) > abs(exact) * Decimal('0.01'))
            or exact != 1 and rounded == 1)


def validate_numeric_comparison(raw, checked, sources):
    mentions = list(MENTION.finditer(checked['summary'].replace('−', '-')))
    if not mentions:
        return
    measurements = raw.get('measurements')
    if not isinstance(measurements, list) or not measurements or len(measurements) > 12:
        raise ValueError('比较数字缺少逐项实验条件，已停止发布。')
    supported = set()
    for measurement in measurements:
        if not isinstance(measurement, dict):
            raise ValueError('比较数字依据格式无效。')
        if not isinstance(measurement.get('sourceId'), str):
            raise ValueError('比较数字的来源标识无效。')
        source = sources.get(measurement['sourceId'])
        packet = source.get('_verifiedTable') if source else None
        if not packet:
            # Explicit author reports in prose remain usable. Their result,
            # dataset and baseline must occur in ONE cited literal passage;
            # hardware is checked independently below in same-paper evidence.
            quote = measurement.get('quote')
            if not source or (source.get('metadata') or {}).get('evidence_kind') == 'table' or raw.get('kind') != 'reported':
                raise ValueError('比较数字没有经过列核对的实验表依据。')
            if not isinstance(quote, str) or not any(ref['sourceId'] == source['sourceId'] and quote == ref['quote'] for ref in checked['references']):
                raise ValueError('比较数字的文字报告缺少连续原文引用。')
            value, unit = _numeric(measurement.get('value'))
            metric = str(measurement.get('metric') or '').upper()
            quoted = {(Decimal(match['value'] or match['score']), _mention_unit(match))
                      for match in MENTION.finditer(quote)}
            if (value, unit or metric) not in quoted:
                raise ValueError('比较数字未在所引文字报告中明确出现。')
            if any(not isinstance(measurement.get(key), str) or not name_key(measurement[key])
                   or name_key(measurement[key]) not in name_key(quote) for key in ('dataset', 'baseline')):
                raise ValueError('文字报告的指标、场景和基线没有连续对应依据。')
            _validate_conditions(measurement, checked, sources, source, measurement['dataset'], measurement['baseline'])
            supported.add((value, unit or metric))
            continue
        if type(measurement.get('row')) is not int or type(measurement.get('group')) is not int:
            raise ValueError('比较数字的实验表行列格式无效。')
        group = measurement['group']
        if not 0 <= group < len(packet['groups']):
            raise ValueError('比较数字的数据集列无效。')
        dataset, metrics = packet['groups'][group]
        metric = measurement.get('metric')
        if metric not in metrics:
            raise ValueError('比较数字的指标列无效。')
        row = next((row for row in packet['rows'] if row[0] == measurement['row']), None)
        baseline = next((row for row in packet['rows'] if row[0] == measurement.get('baselineRow')), None)
        if row is None or baseline is None:
            raise ValueError('比较数字的结果行或基线版本未核对。')
        column = sum(len(group[1]) for group in packet['groups'][:group]) + metrics.index(metric)
        expected, unit = _numeric(row[2][column])
        operation = measurement.get('operation', 'value')
        try:
            value, declared_unit = _numeric(measurement.get('value'))
            if operation != 'value':
                if raw.get('kind') != 'inference':
                    raise ValueError('按表计算的差值或倍数须标为推断，不能当作作者报告。')
                base, base_unit = _numeric(baseline[2][column])
                if base_unit != unit or operation not in ('difference', 'ratio', 'inverse_ratio'):
                    raise ValueError('比较数字的计算口径无效。')
                expected = expected - base if operation == 'difference' else (base / expected if operation == 'inverse_ratio' else expected / base)
                places = -value.as_tuple().exponent
                if not 0 <= places <= 6:
                    raise ValueError('比较数字精度无效。')
                rounded = expected.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
                if operation in ('ratio', 'inverse_ratio') and ratio_rounding_distorts(expected, rounded):
                    raise ValueError('比较比值精度会扭曲原始结果。')
                expected = rounded
                unit = '' if operation in ('ratio', 'inverse_ratio') else unit
            if value != expected or declared_unit != unit:
                raise ValueError('比较数字与核对过的表格单元不一致。')
        except (InvalidOperation, ZeroDivisionError, IndexError) as exc:
            raise ValueError('比较数字的计算依据无效。') from exc
        # Dataset, hardware and baseline are visible in this result cell,
        # with same-paper literal references, rather than a final disclaimer.
        _validate_conditions(measurement, checked, sources, source, dataset, baseline[1])
        for result_row in (row, baseline):
            literal = f"Table row {result_row[0]}: " + ' | '.join([result_row[1], *result_row[2]])
            if not any(ref['sourceId'] == source['sourceId'] and literal in ref['quote'] for ref in checked['references']):
                raise ValueError('比较数字没有引用完整的结果行和基线行。')
        supported.add((value, '倍' if operation in ('ratio', 'inverse_ratio') else unit or metric.upper()))
        if metric.upper() == 'PSNR' and operation not in ('ratio', 'inverse_ratio'):
            supported.add((value, 'DB'))
    for mention in mentions:
        value = Decimal(mention['value'] or mention['score'])
        unit = _mention_unit(mention)
        if (value, unit) not in supported:
            raise ValueError('比较结果含未逐项核对的数字。')


def _validate_conditions(measurement, checked, sources, source, dataset, version):
    hardware = measurement.get('hardware')
    if name_key(measurement.get('dataset')) != name_key(dataset) or name_key(measurement.get('baseline')) != name_key(version):
        raise ValueError('比较数字的场景或基线版本不匹配。')
    if not isinstance(hardware, str) or not re.search(r'GPU|CPU|NVIDIA|AMD|Intel|[RG]TX|Tesla|\b[AH]\d{3,5}\b', hardware, re.I):
        raise ValueError('比较数字的硬件条件无效。')
    if (any(name_key(value) not in name_key(checked['summary']) for value in (dataset, version))
            or not _hardware_display_mentions(checked['summary'], hardware)):
        raise ValueError('比较数字未在本条结果注明场景、硬件和基线。')
    condition = validate_claim({'summary': '实验条件', 'kind': 'reported',
                                'references': measurement.get('conditionReferences')}, list(sources.values()))
    if any(sources[ref['sourceId']]['pdfId'] != source['pdfId'] for ref in condition['references']):
        raise ValueError('比较数字的实验条件引用了其他论文。')
    if not any(name_key(hardware) in name_key(ref['quote']) for ref in condition['references']):
        raise ValueError('比较数字的硬件没有原文依据。')
    refs = [*checked['references'], *condition['references']]
    checked['references'] = list({(ref['sourceId'], ref['quote']): ref for ref in refs}.values())
