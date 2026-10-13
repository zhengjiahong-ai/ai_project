"""有界的 arXiv 发现/全文出口。每次调用仅发送一次请求，无隐藏重试。"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from xml.etree import ElementTree


class AcademicAccessError(ValueError):
    """仅包含固定错误类型，不回显 URL、正文或凭据。"""


def public_addresses(host):
    addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise AcademicAccessError('学术来源地址不可访问')
    return addresses


def pinned_https_get(host, path, max_bytes, *, resolver=public_addresses, timeout=20):
    """解析后固定连接 IP，TLS 仍验证原主机；拒绝全部重定向。"""
    if not ((host == 'export.arxiv.org' and path.startswith('/api/query?'))
            or (host == 'arxiv.org' and path.startswith('/pdf/'))):
        raise AcademicAccessError('学术来源超出允许范围')
    addresses = resolver(host)
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise AcademicAccessError('学术来源地址不可访问')
    connection = http.client.HTTPSConnection(host, timeout=timeout, context=ssl.create_default_context())
    # HTTPSConnection.connect retains the original host for SNI/certificate checks.
    connection._create_connection = lambda _address, timeout=timeout, source_address=None: socket.create_connection(
        (addresses[0], 443), timeout=timeout, source_address=source_address)
    try:
        connection.request('GET', path, headers={'User-Agent': 'PixiuDeepResearch/2.0', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        if response.status != 200:
            raise AcademicAccessError('学术来源暂不可获取')
        declared = response.getheader('Content-Length')
        if declared and (not declared.isdigit() or int(declared) > max_bytes):
            raise AcademicAccessError('学术来源超过大小限制')
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise AcademicAccessError('学术来源超过大小限制')
        return response.getheader('Content-Type', '').split(';')[0].strip().lower(), body
    except AcademicAccessError:
        raise
    except (OSError, http.client.HTTPException, ssl.SSLError) as cause:
        raise AcademicAccessError('学术来源请求未完成') from cause
    finally:
        connection.close()


_ARXIV_ID = re.compile(r'(?:\d{4}\.\d{4,5}|[a-z][a-z.-]+/\d{7})(?:v[1-9]\d*)?\Z', re.I)


def checked_arxiv_id(value):
    if not isinstance(value, str) or not _ARXIV_ID.fullmatch(value):
        raise AcademicAccessError('arXiv 标识无效')
    return value


@dataclass(frozen=True)
class AcademicPolicy:
    enabled: bool = False
    mode: str = 'task_only'
    allow_fulltext: bool = False
    max_results: int = 6
    max_pdf_bytes: int = 8 * 1024 * 1024
    max_pages: int = 100
    parse_seconds: float = 20


class AcademicSourceClient:
    """账本调用 discover/fetch_fulltext；本适配器不递归，不调用模型。"""
    def __init__(self, policy: AcademicPolicy, transport=pinned_https_get, *, cache_dir=None):
        self.policy = policy
        self.transport = transport
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def _require(self, *, fulltext=False):
        if not self.policy.enabled or self.policy.mode not in {'academic_external', 'external_only'}:
            raise AcademicAccessError('本轮未开启外部文献')
        if fulltext and not self.policy.allow_fulltext:
            raise AcademicAccessError('本轮未开启公开全文获取')

    def discover(self, query, limit=6):
        self._require()
        if not isinstance(query, str) or not query.strip() or len(query) > 700:
            raise AcademicAccessError('学术查询无效')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.policy.max_results:
            raise AcademicAccessError('学术查询数量无效')
        # arXiv expects a structured query; raw prose can return unrelated papers.
        # A supplied identifier is a lookup, not a broad keyword search.
        identifiers = list(dict.fromkeys(re.findall(r'(?<![\w.])\d{4}\.\d{4,5}(?:v[1-9]\d*)?(?![\w.])', query)))
        params = {'start': 0, 'max_results': limit}
        if identifiers:
            params['id_list'] = ','.join(identifiers[:limit])
        elif re.search(r'\b(?:all|ti|au|abs|cat):', query):
            params['search_query'] = query.strip()
        else:
            generic = {'paper', 'method', 'methods', 'component', 'components', 'role', 'function',
                       'three', 'study', 'approach', 'the', 'and', 'of', 'for', 'in'}
            words = [word for word in re.findall(r'[\w-]+', query, re.UNICODE)
                     if word.lower() not in generic][:6]
            if not words:
                raise AcademicAccessError('学术查询缺少主题')
            params['search_query'] = ' AND '.join('all:"' + word + '"' for word in words)
        path = '/api/query?' + urlencode(params)
        content_type, body = self.transport('export.arxiv.org', path, 1024 * 1024)
        if content_type not in {'application/atom+xml', 'application/xml', 'text/xml'}:
            raise AcademicAccessError('学术元数据类型无效')
        if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
            raise AcademicAccessError('学术元数据格式无效')
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as cause:
            raise AcademicAccessError('学术元数据格式无效') from cause
        ns = {'a': 'http://www.w3.org/2005/Atom'}
        results, seen = [], set()
        for entry in root.findall('a:entry', ns)[:limit]:
            raw_id = entry.findtext('a:id', '', ns)
            match = re.fullmatch(r'https?://arxiv\.org/abs/(.+)', raw_id)
            if not match:
                continue
            arxiv_id = checked_arxiv_id(match.group(1))
            if identifiers and not any(re.sub(r'v\d+$', '', value) == re.sub(r'v\d+$', '', arxiv_id)
                                       and (not re.search(r'v\d+$', value) or value == arxiv_id) for value in identifiers):
                continue
            if arxiv_id in seen:
                continue
            seen.add(arxiv_id)
            work_id = 'arxiv:' + re.sub(r'v\d+$', '', arxiv_id)
            abstract = ' '.join(entry.findtext('a:summary', '', ns).split())[:10000]
            results.append({'workId': work_id, 'versionId': 'arxiv:' + arxiv_id, 'arxivId': arxiv_id,
                'title': ' '.join(entry.findtext('a:title', '', ns).split())[:1000],
                'abstract': abstract, 'text': abstract, 'accessLevel': 'abstract', 'sourceKind': 'external_academic',
                'url': 'https://arxiv.org/abs/' + arxiv_id,
                'contentHash': hashlib.sha256(abstract.encode()).hexdigest(), 'retrievedAt': time.time()})
        return results

    def fetch_fulltext(self, arxiv_id):
        self._require(fulltext=True)
        arxiv_id = checked_arxiv_id(arxiv_id)
        content_type, body = self.transport('arxiv.org', '/pdf/' + arxiv_id, self.policy.max_pdf_bytes)
        if len(body) > self.policy.max_pdf_bytes or content_type != 'application/pdf' or not body.startswith(b'%PDF-'):
            raise AcademicAccessError('公开全文格式或大小无效')
        try:
            parsed = subprocess.run([sys.executable, '-m', 'services.deep_research_pdf_parser',
                                     str(self.policy.max_pages), str(self.policy.max_pdf_bytes)],
                                    cwd=str(Path(__file__).resolve().parent.parent), input=body,
                                    capture_output=True, timeout=self.policy.parse_seconds, check=False)
            if parsed.returncode != 0 or len(parsed.stdout) > 13_000_000:
                raise AcademicAccessError('公开全文页数、加密状态或解析结果不支持')
            pages = json.loads(parsed.stdout)
            if not any(page['text'].strip() for page in pages):
                raise AcademicAccessError('公开全文未取得可读取正文')
        except subprocess.TimeoutExpired as cause:
            raise AcademicAccessError('公开全文解析超时') from cause
        except AcademicAccessError:
            raise
        except Exception as cause:
            raise AcademicAccessError('公开全文解析未完成') from cause
        content_hash = hashlib.sha256(body).hexdigest()
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            target = self.cache_dir / (content_hash + '.pdf')
            if not target.exists():
                temporary = self.cache_dir / (content_hash + '.' + __import__('uuid').uuid4().hex + '.tmp')
                temporary.write_bytes(body)
                temporary.replace(target)
        return {'workId': 'arxiv:' + re.sub(r'v\d+$', '', arxiv_id), 'versionId': 'arxiv:' + arxiv_id,
            'arxivId': arxiv_id, 'accessLevel': 'fulltext', 'sourceKind': 'external_academic',
            'contentHash': content_hash, 'pages': pages,
            'url': 'https://arxiv.org/pdf/' + arxiv_id, 'retrievedAt': time.time()}
