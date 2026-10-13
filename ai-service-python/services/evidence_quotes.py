"""Bounded literal excerpts that a model can select without rewriting words."""
import hashlib
import json
import re

from services.comparison_measurements import bounded_table_body, verified_packet
from services.focused_evidence import bounded_evidence_body
from services.safety_service import wrap_untrusted_context
from services.experiment_facts import attach_experiment_facts

TABLE_VERIFICATION_PROMPT = '''verifiedTable是按PDF绘制位置逐格核对的行白名单，groups只用于rows列出的完整行。
tableColumnMappingUnverified=true表示原始片段仍有未核对的行或合并单元格，不否定verifiedTable白名单中的行；不能因此把整张表都说成未核对。
数字只取白名单中的结果行与基线行，按groups选择数据集及指标，并核对同论文硬件和实验条件。未列出的行、缺失白名单或损坏单元格不能推测列归属，不能自行拆开合并单元格或外推验证范围。
'''


def excerpt_catalog(source_id, body):
    excerpts = []
    # PDF soft line breaks belong to one continuous sentence. Preserve their
    # exact newlines instead of offering incomplete lines such as "Quantizing
    # all attributes to" as if they were an independent supporting sentence.
    blocks, prose = [], []
    def flush():
        if prose:
            blocks.append('\n'.join(prose))
            prose.clear()
    for line in body.splitlines():
        if line.startswith('[SANITIZED INJECTION-LIKE CONTENT:'):
            flush()
            continue
        if not line.strip():
            flush()
        elif line.startswith(('Table row ', 'Equation:')) or (
                len(re.findall(r'\d+(?:\.\d+)?', line)) >= 4
                and re.search(r'\d(?:\s*%|\s*[KMG]i?B)?\s*$', line, re.I)
                and not re.match(r'\s*(?:Table|Figure)\s+\d', line, re.I)):
            flush()
            blocks.append(line)
        else:
            prose.append(line)
    flush()
    for block in blocks:
        units = [block] if block.startswith('Table row ') else re.split(r'(?<=[。！？])|(?<=[.!?])\s+(?=[A-Z])', block)
        for unit in units:
            rest = unit.strip()
            if len(rest) <= 600 and re.search(r'[.!?。！？]$', rest):
                excerpts.append(rest)
                continue
            while len(rest) > 300:
                end = rest.rfind(' ', 8, 301)
                if end < 8:
                    end = 300
                if len(rest[end:].strip()) < 8:
                    end = len(rest) - 8
                part, rest = rest[:end].strip(), rest[end:].strip()
                excerpts.append(part)
            if len(rest) >= 8:
                excerpts.append(rest)
    return {hashlib.sha256((source_id + '\0' + quote).encode()).hexdigest()[:16]: quote
            for quote in excerpts}


def prepare_quote_sources(sources):
    clean, validation, catalog = [], [], {}
    budget = min(1400, 24000 // max(1, len(sources)))
    for source in sources:
        body = bounded_evidence_body(source.get('text'), budget)
        body, verified = bounded_table_body(source, body, budget)
        if not body or (source.get('metadata') or {}).get('fallback'):
            continue
        sid = source.get('sourceId')
        if not isinstance(sid, str) or not sid or sid in catalog:
            raise ValueError('证据标识重复或无效，请重新检索。')
        literal_body = body
        safe_body = wrap_untrusted_context('Paper body', body, max_tokens=1000)
        body = safe_body['text']
        reserved = len(json.dumps(verified, ensure_ascii=False, separators=(',', ':'))) if verified else 0
        notices = [line for line in body.splitlines() if line.startswith('[SANITIZED INJECTION-LIKE CONTENT:')]
        chosen, displayed, size = {}, list(notices), sum(len(line) + 1 for line in notices)
        candidates = list(excerpt_catalog(sid, body).items())
        def importance(item):
            quote = item[1]
            return (5 * int(quote.startswith(('Equation:', 'Table row ')))
                    + len(re.findall(r'transmittance|normalized|clipping|denot|represent|indicator|opacity|hardware|dataset|baseline|GPU|A6000', quote, re.I)))
        for qid, quote in sorted(candidates, key=importance, reverse=True):
            line = f'[{qid}] {quote}'
            if size + len(line) + 1 + reserved > budget:
                continue
            chosen[qid] = quote
            size += len(line) + 1
        if not chosen:
            continue
        chosen = {qid: quote for qid, quote in candidates if qid in chosen}
        displayed.extend(f'[{qid}] {quote}' for qid, quote in chosen.items())
        shown_body = '\n'.join(chosen.values())
        packet = verified_packet(source, shown_body)
        # Never expose a verified row whose literal text has fallen out of the budget.
        if verified and packet:
            row_ids = {row[0] for row in verified['rows']}
            packet['rows'] = [row for row in packet['rows'] if row[0] in row_ids]
        safe = wrap_untrusted_context('Paper literal excerpts', '\n'.join(displayed), max_tokens=1000)
        if not all(line in safe['text'] for line in displayed):
            raise ValueError('原文摘录被安全包装裁剪，请缩小材料范围。')
        metadata = source.get('metadata') or {}
        clean.append({'sourceId': sid, 'pdfId': source['pdfId'], 'text': safe['wrapped'],
                      'evidenceKind': metadata.get('evidence_kind'), 'verifiedTable': packet,
                      'tableColumnMappingUnverified': bool(metadata.get('table_column_mapping_unverified'))})
        # Two checks prevent a free-form historical quote from stitching across
        # filtered lines. The model selects only the visible catalog excerpts.
        safe_original = '\n'.join(line for line in body.splitlines() if not line.startswith('[SANITIZED INJECTION-LIKE CONTENT:'))
        original = {key: value for key, value in source.items() if key != '_experimentFacts'}
        validation.append({**original, 'text': safe_original, '_literalBody': literal_body, '_verifiedTable': packet})
        catalog[sid] = chosen
    attach_experiment_facts(clean, validation, catalog)
    return clean, validation, catalog


def resolve_references(raw, catalog, *, require_selection=False):
    if not isinstance(raw, dict):
        raise ValueError('结论格式无效。')
    claim = {**raw}
    refs = raw.get('references')
    if not isinstance(refs, list):
        raise ValueError('结论缺少原文依据。')
    resolved = []
    for ref in refs:
        # A bare catalog ID has the same unambiguous literal identity as
        # {quoteId: ID}. Do not accept free quotes or invent an owning source.
        if isinstance(ref, str) and re.fullmatch(r'[0-9a-f]{16}', ref):
            ref = {'quoteId': ref}
        if not isinstance(ref, dict):
            raise ValueError('证据格式无效。')
        sid, qid = ref.get('sourceId'), ref.get('quoteId')
        if qid is not None:
            if 'sourceId' not in ref and isinstance(qid, str):
                owners = [source_id for source_id, quotes in catalog.items() if qid in quotes]
                if len(owners) != 1:
                    raise ValueError('摘录选择不存在或无法唯一确定来源。')
                sid = owners[0]
            quote = catalog.get(sid, {}).get(qid) if isinstance(sid, str) and isinstance(qid, str) else None
            if quote is None or ('quote' in ref and ref['quote'] != quote):
                raise ValueError('摘录选择不存在、归属错误或被改写。')
            resolved.append({'sourceId': sid, 'quote': quote})
        elif require_selection:
            raise ValueError('请从给定正文选择摘录，不要重新生成引用。')
        else:
            # Historical literal JSON remains auditable through validate_claim.
            resolved.append(ref)
    claim['references'] = resolved
    measurements = raw.get('measurements')
    if isinstance(measurements, list):
        claim['measurements'] = []
        for item in measurements:
            if not isinstance(item, dict):
                raise ValueError('数字依据格式无效。')
            measurement = {**item}
            if 'quoteId' in item:
                selected = resolve_references({'references': [item]}, catalog, require_selection=require_selection)['references'][0]
                measurement.update(sourceId=selected['sourceId'], quote=selected['quote'])
            if 'conditionReferences' in item:
                measurement['conditionReferences'] = resolve_references({'references': item['conditionReferences']}, catalog, require_selection=require_selection)['references']
            claim['measurements'].append(measurement)
    bindings = raw.get('numericBindings')
    if isinstance(bindings, list):
        claim['numericBindings'] = []
        for item in bindings:
            if not isinstance(item, dict):
                raise ValueError('数值绑定格式无效。')
            binding = {**item}
            if item.get('kind') in ('method_parameter', 'author_report'):
                selected = resolve_references({'references': [item]}, catalog,
                                              require_selection=True)['references'][0]
                binding.update(sourceId=selected['sourceId'], quote=selected['quote'])
            if 'conditionReferences' in item:
                binding['conditionReferences'] = resolve_references(
                    {'references': item['conditionReferences']}, catalog,
                    require_selection=True)['references']
            claim['numericBindings'].append(binding)
    return claim
