"""Readable display for already verified literals; no evidence repair or rounding."""
import re

LIMITS = {
    'over': ('gt', '超过'), 'more than': ('gt', '超过'), '>': ('gt', '超过'),
    'at least': ('ge', '至少'), '>=': ('ge', '至少'), '≥': ('ge', '至少'),
    'less than': ('lt', '低于'), '<': ('lt', '低于'),
    'at most': ('le', '不超过'), 'up to': ('le', '不超过'), '<=': ('le', '不超过'), '≤': ('le', '不超过'),
    'about': ('approx', '约'), 'approximately': ('approx', '约'), '≈': ('approx', '约'), '~': ('approx', '约'),
}
CHINESE_LIMITS = {'超过': 'gt', '高于': 'gt', '大于': 'gt', '至少': 'ge', '不低于': 'ge',
                  '低于': 'lt', '少于': 'lt', '小于': 'lt', '不超过': 'le', '至多': 'le',
                  '最多': 'le', '约': 'approx', '大约': 'approx', '近似': 'approx'}
NUMBER_UNIT = r'\d+(?:\.\d+)?\s*(?:%|％|FPS|frames?\s*(?:per second|/\s*s)|[KMG]i?B|dB|倍|p)'
METRIC = re.compile(r'(?P<metric>PSNR|SSIM|LPIPS)\s+(?P<direction>increase|decrease|loss|drop)'
                    r'\s+(?:of\s+)?(?P<only>only\s+)?(?P<number>\d+(?:\.\d+)?)'
                    r'(?P<unit>\s+dB)?(?:\s+on\s+(?P<dataset>[A-Za-z0-9 -]+))?', re.I)
METRIC_PREFIX = re.compile(r'(?P<metric>PSNR|SSIM|LPIPS)\s*(?P<direction>变化为|上升|增加|提升|下降|减少|降低)'
                           r'(?P<only>仅|只有)?\s*$', re.I)
LIMIT_PREFIX = re.compile('(' + '|'.join(sorted(CHINESE_LIMITS, key=len, reverse=True)) + r')\s*$')


def render_author_quantity(template, key, literal):
    """Normalize known grammar only after literal/source validation has passed.

    The literal and all source references remain unchanged. Unsupported phrases
    are explicitly quoted verbatim. Nearby incompatible directions/limits are
    rejected, never rewritten into a supported claim.
    """
    token = f'⟦数值{key}⟧'
    position = template.index(token)
    prefix = template[:position]
    suffix = template[position:]
    metric = METRIC.fullmatch(literal)
    if metric:
        direction = '上升' if metric['direction'].lower() == 'increase' else '下降'
        adjacent = METRIC_PREFIX.search(prefix)
        if adjacent:
            actual = direction if adjacent['direction'] == '变化为' else (
                '上升' if adjacent['direction'] in ('上升', '增加', '提升') else '下降')
            if adjacent['metric'].upper() != metric['metric'].upper() or actual != direction:
                raise ValueError('作者报告的指标或变化方向与原文不一致。')
            if adjacent['only'] and not metric['only']:
                raise ValueError('作者报告增加了原文未提供的限定词。')
            prefix = prefix[:adjacent.start()]
        display = metric['metric'].upper() + ('仅' if metric['only'] else '') + direction + metric['number']
        if metric['unit']:
            display += metric['unit']
        if metric['dataset']:
            dataset = metric['dataset'].strip()
            # The exact same dataset is already displayed next to this fact.
            # Aliases or a name elsewhere in a different sentence do not qualify.
            nearby = prefix.split('。')[-1]
            if not re.search(r'(?:在\s*)?' + re.escape(dataset) + r'\s*(?:上|中)[^。！？；;]{0,24}$', nearby):
                display += f'（{dataset}）'
        return prefix + suffix, display

    span = re.fullmatch(r'from\s+(' + NUMBER_UNIT + r')\s+to\s+(' + NUMBER_UNIT + ')', literal, re.I)
    if span:
        if prefix.endswith('从'):
            template = prefix[:-1] + suffix
        elif prefix.endswith('变化为'):
            template = prefix[:-3] + suffix
        return template, f'从{span[1]}到{span[2]}'

    quantity = re.fullmatch(r'(?P<limit>at least|at most|more than|less than|up to|over|about|approximately|>=|<=|[>≥<≤≈~])?'
                            r'\s*(?P<quantity>' + NUMBER_UNIT + r')(?P<scene>\s+on complex scenes)?', literal, re.I)
    if quantity:
        limit = LIMITS.get((quantity['limit'] or '').lower())
        adjacent = LIMIT_PREFIX.search(prefix)
        if adjacent:
            if not limit or CHINESE_LIMITS[adjacent[1]] != limit[0]:
                raise ValueError('作者报告的数量上下界与原文不一致。')
            prefix = prefix[:adjacent.start()]
        # Preserve symbolic comparators in their familiar compact notation.
        if quantity['limit'] in ('>=', '<=', '>', '<', '≥', '≤', '≈', '~'):
            display = quantity['limit'] + quantity['quantity']
        else:
            display = (limit[1] if limit else '') + quantity['quantity']
        if quantity['scene'] and not re.search(r'复杂场景[^。！？；;]{0,24}$', prefix):
            display += '（复杂场景）'
        return prefix + suffix, display

    return template, f'原文「{literal}」'
