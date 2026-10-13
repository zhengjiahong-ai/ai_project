"""Bounded local PDF retrieval when the vector backend is unavailable."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import requests

from services.deep_research.contracts import DeepResearchError

MAX_LOCAL_PDF_BYTES = 64 * 1024 * 1024

class LocalTaskRetriever:
    def __init__(self, repo, run_id, validate, *, origin, get=requests.get, parse=None):
        self.repo, self.run_id, self.validate = repo, run_id, validate
        self.origin, self.get = origin.rstrip('/'), get
        self.parse = parse or _parse_pdf
        self.pages = {}
        self.index_tables = {}

    def __call__(self, query, pdf_id, *, limit=5):
        if not self.validate(self.run_id, pdf_id):
            raise DeepResearchError("scope_revoked", "论文范围已变更")
        # Keep the existing indexed route where its runtime is installed.
        if importlib.util.find_spec('sentence_transformers') is not None:
            try:
                from services.research_executor import retrieve_current_paper_evidence
                items = retrieve_current_paper_evidence(query, pdf_id, limit=limit, allow_query_rewrite=False)
                if items:
                    indexed = [_indexed_source(item) for item in items]
                    metrics = _requested_metrics(query)
                    if metrics and limit > 1:
                        from services.tools.retrieval_tools import get_rag
                        from services.evidence_service import normalize_evidence_items
                        if pdf_id not in self.index_tables:
                            rag = get_rag()
                            owned = rag.normalize_id(pdf_id)
                            raw = rag.get_documents_by_metadata({'id': owned}, limit=400)
                            # Recheck owner even if a backend ignores its metadata filter.
                            raw = [row for row in raw if row.get('metadata', {}).get('id') == owned
                                   and row.get('metadata', {}).get('table_verified_data')]
                            normalized = normalize_evidence_items(raw, source_type='current_paper',
                                pdf_id=owned, max_text_chars=2000)
                            self.index_tables[pdf_id] = [_indexed_source(row) for row in normalized]
                        indexed = _include_metric_tables(indexed, self.index_tables[pdf_id], query, metrics, limit)
                    return indexed
            except (ImportError, RuntimeError, OSError):
                pass
        material, pages = self.load_pages(pdf_id)
        passages = []
        for page in pages:
            text = page.get('text', '')
            for offset in range(0, len(text), 1500):
                passage = text[offset:offset + 1800]
                if passage.strip():
                    location = {'page': page['page'], 'offset': offset}
                    identity = hashlib.sha256(f"{pdf_id}:{material['contentHash']}:{location}".encode()).hexdigest()
                    passages.append({'sourceId': 'src_' + identity, 'pdfId': pdf_id, 'text': passage,
                        'location': location, 'contentHash': material['contentHash'], 'versionId': material.get('versionId'),
                        'title': material.get('title', pdf_id), 'accessLevel': 'fulltext', 'retrievalMode': 'pdf_lexical_fallback'})
        scores = _bm25(query, [value['text'] for value in passages])
        ranked = sorted(zip(scores, passages), key=lambda value: -value[0])
        return [value for score, value in ranked[:min(max(int(limit), 0), 5)] if score > 0]


    def load_pages(self, pdf_id):
        """Read only the owned snapshot version; recheck scope even on cache hits."""
        if not self.validate(self.run_id, pdf_id):
            raise DeepResearchError("scope_revoked", "论文范围已变更")
        record = self.repo.require_run(self.run_id)
        material = next((value for value in record.get('materials', []) if value.get('materialId') == pdf_id), None)
        if not material or not material.get('contentHash'):
            raise DeepResearchError("source_missing", "论文版本未保存")
        key = (pdf_id, material['contentHash'])
        if key not in self.pages:
            url = f"{self.origin}/task-workspaces/{quote(record['taskId'], safe='')}/materials/{quote(pdf_id, safe='')}/file"
            with self.get(url, timeout=20, stream=True, allow_redirects=False) as response:
                if response.status_code != 200:
                    raise DeepResearchError('source_unavailable', '论文文件暂不可读取')
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_LOCAL_PDF_BYTES:
                        raise DeepResearchError('source_too_large', '论文超过正文回查大小上限')
                    chunks.append(chunk)
            body = b''.join(chunks)
            if not body.startswith(b'%PDF-') or hashlib.sha256(body).hexdigest() != material['contentHash']:
                raise DeepResearchError('source_changed', '论文内容与研究快照不同')
            self.pages[key] = self.parse(body)
        return material, self.pages[key]


def _requested_metrics(query):
    aliases = {
        'FPS': r'\bfps\b|rendering (?:speed|performance)|渲染速度|帧率',
        'PSNR': r'\bpsnr\b', 'SSIM': r'\bssim\b', 'LPIPS': r'\blpips\b',
        'SIZE': r'\b(?:storage|memory|size|compression)\b|存储|大小|压缩|显存',
    }
    return {metric for metric, pattern in aliases.items() if re.search(pattern, query, re.I)}


def _include_metric_tables(indexed, tables, query, metrics, limit):
    """Reserve at most two slots for relevant verified rows, keeping prose context.

    This is retrieval only: neither table validity nor ranking establishes that
    a measurement answers the question. Later relevance and claim checks remain.
    """
    ranked = []
    scores = _bm25(query, [row.get('text', '') for row in tables])
    for row, score in zip(tables, scores):
        packet = row.get('tableData')
        if not packet:
            continue
        headers = {m.upper() for _, group in packet['groups'] for m in group}
        if headers & {'MEM', 'MEMORY', 'STORAGE'}:
            headers.add('SIZE')
        overlap = len(headers & metrics)
        if not overlap:
            continue
        own_result = any(re.match(r'^ours(?:\b|_)', method, re.I) for _, method, _ in packet['rows'])
        ranked.append((overlap, own_result, score, row))
    ranked.sort(key=lambda item: item[:3], reverse=True)
    chosen = [item[3] for item in ranked[:min(2, limit - 1)]]
    if not chosen:
        return indexed
    ids = {row['sourceId'] for row in chosen}
    # Keep the best original prose first. Do not spend an extra slot on a table
    # already returned by hybrid retrieval; every source retains its identity.
    rest = [row for row in indexed if row['sourceId'] not in ids]
    return rest[:1] + chosen + rest[1:max(1, limit - len(chosen))]


def _indexed_source(item):
    """Adapt legacy index metadata to the versioned research location contract."""
    metadata = item.get('metadata') or {}
    location = dict(item.get('location') or {})
    page = metadata.get('page')
    page_index = item.get('pageIndex', metadata.get('page_index'))
    if isinstance(page, int) and not isinstance(page, bool) and page > 0:
        location.setdefault('page', page)
    elif isinstance(page_index, int) and not isinstance(page_index, bool) and page_index >= 0:
        location.setdefault('page', page_index + 1)
    for key, value in [('chunk', item.get('chunkIndex', metadata.get('chunk_index'))),
                       ('section', metadata.get('section_title')), ('table', metadata.get('table_id'))]:
        if value is not None:
            location.setdefault(key, value)
    if metadata.get('table_column_mapping_unverified') is True:
        location['tableColumnMappingUnverified'] = True
    from services.deep_research.table_evidence import visible_table_packet
    packet = visible_table_packet(metadata.get('table_verified_data'), item.get('text', ''))
    return {**item, 'tableData': packet, 'location': location, 'title': item.get('title') or metadata.get('title', ''),
            'retrievalMode': 'indexed_hybrid'}


def _tokens(text):
    return re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]{2}', text.lower())


def _bm25(query, documents):
    tokenized = [_tokens(text) for text in documents]
    average = sum(map(len, tokenized)) / max(len(tokenized), 1) or 1
    terms = set(_tokens(query)) - {'the', 'and', 'for', 'with', 'this', 'that', 'from', 'what', 'how', 'does'}
    frequency = {term: sum(term in tokens for tokens in tokenized) for term in terms}
    scores = []
    for tokens in tokenized:
        score = 0
        for term in terms:
            count = tokens.count(term)
            if count:
                idf = math.log(1 + (len(documents) - frequency[term] + .5) / (frequency[term] + .5))
                score += idf * count * 2.2 / (count + 1.2 * (.25 + .75 * len(tokens) / average))
        scores.append(score)
    return scores


def _parse_pdf(body):
    process = subprocess.run([sys.executable, '-m', 'services.deep_research_pdf_parser', '100', str(MAX_LOCAL_PDF_BYTES)],
        cwd=str(Path(__file__).resolve().parents[2]), input=body, capture_output=True, timeout=20, check=False)
    if process.returncode or len(process.stdout) > 13_000_000:
        raise DeepResearchError('source_parse_failed', '论文正文回查未完成')
    return json.loads(process.stdout)
