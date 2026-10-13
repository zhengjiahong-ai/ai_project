"""Local selection of bounded, unchanged definition and experiment passages."""
import re
from services.evidence_service import evidence_section_key, select_section_diverse_evidence
from services.research_synthesis import evidence_body

TOPICS = (
    (('剪枝', 'prun'), ('pruning', 'prune')),
    (('球谐', 'sh ', 'spherical harmonic', 'distill'), ('spherical harmonics', 'distillation', 'distill')),
    (('量化', 'quantiz'), ('quantization', 'quantize')),
    (('显著性', '重要性', 'significance'), ('significance',)),
    (('压缩', 'compress'), ('compression', 'compress')),
    (('速度', 'fps', 'speed'), ('fps', 'speed')),
    (('质量', '画质', 'quality', 'psnr', 'ssim', 'lpips'), ('quality', 'psnr', 'ssim', 'lpips')),
    (('泛化', '视角', 'generaliz', 'view'), ('generalization', 'view', 'camera')),
    (('实验', 'experiment'), ('experiment',)),
    (('硬件', 'hardware'), ('hardware', 'gpu')),
    (('数据集', 'dataset'), ('dataset',)),
)
CONTEXT_SIGNALS = re.compile(
    r'equation:|\beq\.?\s*\d|\bdefined\b|\bnormalized\b|\bcalculated\b|\bdenoted\b'
    r'|\btransmittance\b|\bimplementation details\b|\bGPU\b|\b(?:dataset|baseline)\b'
    r'|\b(?:table|tab\.)\s*\d|\b(?:FPS|PSNR|SSIM|LPIPS)\b'
    r'|\b\d+(?:\.\d+)?\s*(?:MB|GB|FPS)\b', re.I)
METHOD_SECTION = re.compile(
    r'method|approach|prun|distill|quantiz|represent|formulat|optimiz|algorithm|model', re.I)


def focus_groups(question):
    text = str(question or '').lower()
    groups = [terms for triggers, terms in TOPICS if any(trigger in text for trigger in triggers)]
    latin = tuple(dict.fromkeys(re.findall(r'[a-z][a-z0-9_-]{2,}', text)))
    if latin:
        groups.append(latin)
    return groups


def _key(item):
    return (item.get('pdfId'), item.get('chunkIndex')) if item.get('chunkIndex') is not None else item.get('sourceId') or item.get('text')


def _body(item):
    return evidence_body(item.get('text')).lower()


def _matches(item, terms):
    return any(term in _body(item) for term in terms)


def _is_experiment(item):
    section = str(evidence_section_key(item) or '').lower()
    if (item.get('metadata') or {}).get('evidence_kind') == 'table':
        return bool(re.search(r'\b(?:FPS|PSNR|SSIM|LPIPS|accuracy|dataset|baseline)\b', _body(item), re.I))
    return any(term in section for term in ('experiment', 'result', 'ablation', 'evaluation'))


def select_focused_evidence(retrieved, documents, question, axis, limit=6, section_cap=1):
    """Reserve related originals within the existing count, never join or rewrite them."""
    groups = focus_groups(question)
    if not groups or axis not in ('methods', 'experiments', 'compare'):
        return select_section_diverse_evidence(retrieved, limit, section_cap)
    pool, seen = [], set()
    for item in [*documents, *retrieved]:
        key = _key(item)
        if key not in seen and evidence_body(item.get('text')):
            seen.add(key); pool.append(item)
    selected, selected_keys = [], set()
    def add(item):
        if item is not None and len(selected) < limit and _key(item) not in selected_keys:
            selected.append(item); selected_keys.add(_key(item))
    def score(item):
        body = _body(item)
        section = str(evidence_section_key(item) or '').lower()
        hits = sum(_matches(item, group) for group in groups)
        section_hits = sum(any(term in section for term in group) for group in groups)
        extra_results = bool(re.search(r'\b(?:more|additional|supplementary|appendix)\b', section))
        table_bonus = 6 if (item.get('metadata') or {}).get('evidence_kind') == 'table' else 0
        return hits * 2 + section_hits * 5 + len(re.findall(r'equation:', body)) * 4 + len(CONTEXT_SIGNALS.findall(body)) + table_bonus - 12 * extra_results
    def method_section(item):
        section = str(evidence_section_key(item) or '')
        return bool(METHOD_SECTION.search(section)) and not re.search(
            r'introduction|related work|background|reference|appendix', section, re.I)
    method_pool = [item for item in pool if (item.get('metadata') or {}).get('evidence_kind') != 'table' and not _is_experiment(item) and (
        any(_matches(item, group) for group in groups) or (axis == 'compare' and method_section(item)))]
    if axis in ('methods', 'compare') and method_pool:
        anchor = max(method_pool, key=score)
        add(anchor)
        index = anchor.get('chunkIndex')
        if isinstance(index, int):
            adjacent = [item for item in pool if item.get('pdfId') == anchor.get('pdfId')
                and evidence_section_key(item) is not None
                and evidence_section_key(item) == evidence_section_key(anchor)
                and isinstance(item.get('chunkIndex'), int) and 0 < abs(item['chunkIndex'] - index) <= 2]
            for item in sorted(adjacent, key=lambda item: abs(item['chunkIndex'] - index))[:2]:
                add(item)
        for group in groups:
            candidates = [item for item in method_pool if _matches(item, group)]
            named = [item for item in candidates if any(term in str(evidence_section_key(item) or '').lower() for term in group)]
            if any(any(term in str(evidence_section_key(item) or '').lower() for term in group) for item in selected):
                continue
            if not named and any(_matches(item, group) for item in selected):
                continue
            if candidates:
                add(max(named or candidates, key=score))
        if axis == 'compare':
            # A broad comparison may name one concept without listing every
            # module. Reserve distinct method sections before filling results.
            # Four slots remain for experimental conditions, within the old cap.
            sections = {evidence_section_key(item) for item in selected}
            for item in sorted(method_pool, key=score, reverse=True):
                section = evidence_section_key(item)
                if len(selected) >= max(0, limit - 4):
                    break
                if method_section(item) and section not in sections:
                    add(item)
                    sections.add(section)
    if axis in ('experiments', 'compare'):
        for facet, pattern in enumerate((
            r'\bGPU\b|\bhardware\b|implementation details',
            r'\bdataset\b|\bbaseline\b|experimental settings|experimental setup',
            r'quantitative results|\bFPS\b|\bPSNR\b|\bSSIM\b|\bLPIPS\b',
            r'ablation|significance criteria',
        )):
            candidates = [item for item in pool if _is_experiment(item) and re.search(pattern, _body(item) + ' ' + str(evidence_section_key(item)), re.I)]
            if facet < 2:
                # Prefer implementation/settings prose over a noisy extracted
                # table caption. One passage may cover both conditions.
                if any(_is_experiment(item) and re.search(pattern, _body(item), re.I) for item in selected):
                    continue
                prose = [item for item in candidates if (item.get('metadata') or {}).get('evidence_kind') != 'table']
                candidates = prose or candidates
            if facet == 2:
                main_tables = [item for item in candidates if (item.get('metadata') or {}).get('evidence_kind') == 'table'
                               and re.search(r'compar|benchmark|quantitative', str(evidence_section_key(item)), re.I)
                               and not re.search(r'ablation', str(evidence_section_key(item)), re.I)]
                # A repeated header alone does not supply the proposed method
                # or baseline values. Prefer the actual method rows.
                method_rows = [item for item in main_tables if re.search(r'\b(?:ours|proposed)\b', _body(item))]
                candidates = method_rows or main_tables or candidates
            if candidates:
                ranked = sorted(candidates, key=score, reverse=True)
                add(next((item for item in ranked if _key(item) not in selected_keys), ranked[0]))
        if axis == 'experiments':
            for item in sorted([item for item in pool if _is_experiment(item)], key=score, reverse=True):
                add(item)
    sections = {evidence_section_key(item) for item in selected if evidence_section_key(item)}
    for item in retrieved:
        section = evidence_section_key(item)
        if section and section in sections:
            continue
        add(item)
        if section:
            sections.add(section)
    return selected


def bounded_evidence_body(text, budget):
    """Pick one continuous window instead of always discarding late conditions."""
    body = evidence_body(text)
    if len(body) <= budget:
        return body
    starts = {0, len(body) - budget}
    for match in CONTEXT_SIGNALS.finditer(body):
        starts.add(max(0, min(len(body) - budget, match.start() - budget // 3)))
    start = max(sorted(starts), key=lambda pos: len(CONTEXT_SIGNALS.findall(body[pos:pos + budget])))
    return body[start:start + budget].strip()


def select_critique_evidence(retrieved, documents, question, limit=10):
    """Reserve direct evaluation and counterevidence before mechanism exposition.

    Selection controls coverage, not whether the paper's claims are true. Original
    packets, experiment table metadata and literal identity remain unchanged.
    """
    pool, seen = [], set()
    for item in [*retrieved, *documents]:
        key = _key(item)
        if key not in seen and evidence_body(item.get('text')):
            pool.append(item)
            seen.add(key)
    groups = focus_groups(question)
    def relevance(item):
        return sum(_matches(item, group) for group in groups)
    selected, keys = [], set()
    def add(item):
        if item is not None and len(selected) < limit and _key(item) not in keys:
            selected.append(item)
            keys.add(_key(item))
    experimental = bool(re.search(r'画质|质量|性能|速度|压缩|实验|比较|消融|公平|几乎不变|quality|performance|experiment|compar|ablation|fps|psnr|ssim|lpips', question, re.I))
    broad = bool(re.search(r'整体|全面|审稿|批判阅读|贡献.*局限', question))
    if experimental or broad:
        experiments = select_focused_evidence(retrieved, pool, question, 'experiments', limit=min(5, limit), section_cap=2)
        for item in experiments:
            if _is_experiment(item):
                add(item)
    counter = [item for item in pool if re.search(r'limitation|failure|fail(?:s|ed|ure)?|trade.?off|degrad|challeng|less effective|cannot|局限|失败|代价',
                                                  _body(item) + ' ' + str(evidence_section_key(item)), re.I)
               and not re.search(r'related work|references', str(evidence_section_key(item)), re.I)]
    if counter:
        add(max(counter, key=lambda item: (relevance(item), bool(re.search(r'limitation|failure', str(evidence_section_key(item)), re.I)))))
    methods = select_focused_evidence(retrieved, pool, question, 'methods', limit=limit, section_cap=2)
    for item in methods:
        add(item)
    for item in sorted(pool, key=relevance, reverse=True):
        add(item)
    return selected
