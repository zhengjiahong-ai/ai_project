"""Bound prompt size while retaining different papers and research obligations."""
from collections import deque
import json
import re


def comparison_evidence_order(evidence, paper_titles):
    """Prefer a paper's own verified results before background baselines.

    This is prompt selection only, never a relevance or truth verdict. Retain
    every candidate and use the existing paper/obligation balancing afterwards.
    """
    from services.deep_research.table_evidence import visible_table_packet
    def rank(item):
        packet = visible_table_packet(item.get('tableData'), item.get('quote', ''))
        if not packet:
            return 1
        title = paper_titles.get(item.get('sourceWorkId'), '') or item.get('sourceTitle', '')
        title_key = re.sub(r'[^a-z0-9]', '', title.casefold())
        for _, method, _ in packet['rows']:
            method_key = re.sub(r'[^a-z0-9]', '', method.casefold())
            if re.match(r'^ours(?:\b|_)', method, re.I) or (len(method_key) >= 4 and title_key.startswith(method_key)):
                return 0
        return 2
    return sorted(evidence, key=rank)


def surrounding_context(evidence, window=240):
    """Keep bounded sentence context so contrast subjects survive extraction."""
    from services.deep_research.quote_context import quote_context
    return quote_context(evidence, window)


def bounded_evidence_rows(rows, max_bytes=14000):
    """Preserve complete quotes before spending remaining space on context.

    A long context must not silently displace another candidate's whole quote.
    Omitted context is explicit; downstream checks must not resolve an unknown
    subject by inventing the missing antecedent.
    """
    selected = []
    contexts = []
    for row in rows:
        context = row.get('sourceContext')
        compact = {**row, 'sourceContext': {}, 'contextOmitted': True} if context else dict(row)
        candidate = [*selected, compact]
        if len(json.dumps(candidate, ensure_ascii=False).encode('utf-8')) <= max_bytes:
            selected.append(compact)
            contexts.append(context)
    for i, context in enumerate(contexts):
        if not context:
            continue
        expanded = {**selected[i], 'sourceContext': context}
        expanded.pop('contextOmitted', None)
        candidate = [*selected[:i], expanded, *selected[i + 1:]]
        if len(json.dumps(candidate, ensure_ascii=False).encode('utf-8')) <= max_bytes:
            selected[i] = expanded
    return selected


def balanced_sample(items, key, limit):
    groups = {}
    for item in items:
        groups.setdefault(key(item), deque()).append(item)
    selected = []
    while groups and len(selected) < limit:
        for group in list(groups):
            selected.append(groups[group].popleft())
            if not groups[group]:
                del groups[group]
            if len(selected) == limit:
                break
    return selected
