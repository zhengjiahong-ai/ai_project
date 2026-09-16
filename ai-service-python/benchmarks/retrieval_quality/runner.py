"""本地 RAG 检索质量基准 runner。

走运行中服务的 HTTP API（POST /api/rag/retrieve），因此测的是完整链路：
FastAPI -> rag_service -> rag.store -> HybridRetriever -> LiteratureRAG。
不另起进程打开 chroma 的持久化目录，避免与服务进程争锁。

三个核心指标：

1. 跨语言召回 —— 中文提问检索英文论文，top-1/top-3 是否落在正确论文；同时跑一遍
   人工标注的英文等价查询作为"跨语言上限"对照，两者的差距就是改写能吃掉的空间。
2. 坍缩度 —— 中文 top-1 的目标分布是否集中于单一文档。这一项必须看，因为它会
   让名义命中率骗人：实测改写前 10 个中文查询有 7 个 top-1 落在同一篇仅占库
   15% chunk 的论文上，其中 2 个"命中"纯粹是坍缩目标恰好等于期望答案的假阳性。
   本 runner 自动把这类命中扣掉，给出 effectiveTop1。
3. BM25 非零命中 —— 中文查询在英文语料上词汇完全不重叠，改写前恒为 0 路；
   改写后应恢复成有效补召回。

用法（容器内）::

    docker exec ai_service_python sh -lc "cd /app && python -m benchmarks.retrieval_quality.runner"

做改写开关的严格 A/B：在 docker-compose.yml 里给 ai-service 设
``PIXIU_QUERY_REWRITE_ENABLED=0`` 后重建容器跑一遍，再设回 1 跑一遍，对比两份
results.json 的 zh 指标。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_FIXTURES = HERE / "fixtures.json"
DEFAULT_OUTPUT = HERE / "retrieval-quality-results.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DB_PATH = "/app/chroma_data/chroma.sqlite3"
# 当前生效的 collection（与嵌入模型绑定，见 core/rag_vector_db 的模型候选顺序）。
# 旧的 literature_collection_v3 仍在库里但不生效，不能把它的论文算进来。
DEFAULT_COLLECTION = "literature_collection_v4_e5_small"

# 中文 top-1 的众数占比超过此值即判定为坍缩。随机分布下 7 篇论文该值约 0.14，
# 实测改写前是 0.7，阈值取中间偏保守的位置。
COLLAPSE_RATIO = 0.4

# 服务默认全局限流 60 req/min/IP，本 runner 一轮要发二十多个请求，
# 主动节流 + 按 Retry-After 退避，避免把时间浪费在 429 上。
REQUEST_INTERVAL = 0.4
RATE_LIMIT_RETRIES = 10


def load_fixtures(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def retrieve(base_url: str, query: str, top_k: int, timeout: float) -> dict[str, Any]:
    """调一次检索端点，返回顶层响应（含 results / searchQuery / queryRewritten）。"""
    url = f"{base_url.rstrip('/')}/api/rag/retrieve?" + urllib.parse.urlencode(
        {"query": query, "top_k": top_k}
    )

    for _ in range(RATE_LIMIT_RETRIES):
        request = urllib.request.Request(url, data=b"", method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            time.sleep(float(error.headers.get("Retry-After") or 10) + 0.5)
    raise RuntimeError("rate-limit retries exhausted")


def paper_label(item: dict[str, Any], papers: list[dict[str, str]]) -> str:
    """把一条检索结果映射成 fixtures 里的论文标签。"""
    title = str((item.get("metadata") or {}).get("title") or "").lower()
    for paper in papers:
        if str(paper.get("matchTitle", "")).lower() in title:
            return str(paper.get("label"))
    return title[:40] or "?"


def corpus_labels(db_path: str, collection: str, papers: list[dict[str, str]]) -> set[str]:
    """只读 chroma 的 sqlite，取指定 collection 里实际存在哪些论文。

    库中没有的期望论文必须从命中率分母里剔除，否则换一批语料后指标会被
    系统性地压低，看起来像检索退化。取不到清单时返回空集，调用方据此
    退化为“不剔除任何 case”。
    """
    path = Path(db_path)
    if not path.is_file():
        return set()

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = conn.execute(
            "select em.string_value from embedding_metadata em "
            "join embeddings e on em.id = e.id "
            "join segments s on e.segment_id = s.id "
            "join collections c on c.id = s.collection "
            "where em.key = 'title' and c.name = ? "
            "group by em.string_value",
            (collection,),
        ).fetchall()
        conn.close()
    except sqlite3.Error as error:
        print(f"  警告：读不到 {collection} 的论文清单（{error}），本轮不剔除任何 case")
        return set()

    titles = [str(row[0] or "").lower() for row in rows]
    labels = set()
    for paper in papers:
        needle = str(paper.get("matchTitle", "")).lower()
        if needle and any(needle in title for title in titles):
            labels.add(str(paper.get("label")))
    return labels


def run_cases(
    cases: list[dict[str, Any]],
    query_field: str,
    papers: list[dict[str, str]],
    available: set[str],
    base_url: str,
    top_k: int,
    timeout: float,
) -> list[dict[str, Any]]:
    records = []
    for case in cases:
        query = str(case.get(query_field) or "")
        if not query:
            continue

        expect_key = str(case.get("expectPaper") or "")
        expect = next(
            (str(p["label"]) for p in papers if str(p.get("matchTitle", "")).lower() == expect_key.lower()),
            expect_key,
        )
        skipped = bool(available) and expect not in available

        response = retrieve(base_url, query, top_k, timeout)
        time.sleep(REQUEST_INTERVAL)

        results = response.get("results") or {}
        fused = results.get("fused") or []
        labels = [paper_label(item, papers) for item in fused]

        records.append(
            {
                "id": case.get("id"),
                "query": query,
                "expect": expect,
                "skipped": skipped,
                "top": labels[:top_k],
                "hitTop1": bool(labels) and labels[0] == expect,
                "hitTop3": expect in labels[:3],
                "bm25Count": len(results.get("bm25") or []),
                "bm25NonZero": len(results.get("bm25") or []) > 0,
                "searchQuery": response.get("searchQuery"),
                "queryRewritten": bool(response.get("queryRewritten")),
            }
        )
        mark = "skip" if skipped else ("OK  " if records[-1]["hitTop1"] else ("~   " if records[-1]["hitTop3"] else "MISS"))
        print(f"    [{mark}] {query[:30]:32s} 期望={expect:12s} top={labels[:3]} bm25={len(results.get('bm25') or [])}")

    return records


def score(records: list[dict[str, Any]]) -> dict[str, Any]:
    """命中率 + 坍缩度 + 假阳性扣除。"""
    scored = [record for record in records if not record["skipped"]]
    total = len(scored)
    top1 = [record for record in scored if record["hitTop1"]]

    counter = Counter(record["top"][0] for record in scored if record["top"])
    collapse_target, collapse_count = (counter.most_common(1) or [(None, 0)])[0]
    collapse_ratio = collapse_count / total if total else 0.0
    collapsed = collapse_ratio >= COLLAPSE_RATIO and total > 1

    # 坍缩成立时，凡是"期望答案恰好等于坍缩目标"的命中都不可信：
    # 无论问什么都会返回那篇论文，命中只是撞上了。
    suspect = [
        record["id"]
        for record in top1
        if collapsed and record["expect"] == collapse_target
    ]

    return {
        "total": total,
        "skipped": len(records) - total,
        "top1": len(top1),
        "top3": sum(1 for record in scored if record["hitTop3"]),
        "effectiveTop1": len(top1) - len(suspect),
        "collapseTarget": collapse_target if collapsed else None,
        "collapseRatio": round(collapse_ratio, 3),
        "collapsed": collapsed,
        "suspectedFalsePositives": suspect,
        "top1Distribution": dict(counter),
        "bm25NonZero": sum(1 for record in scored if record["bm25NonZero"]),
        "rewritten": sum(1 for record in scored if record["queryRewritten"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="本地 RAG 检索质量基准")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--base-url", default=os.environ.get("PIXIU_AI_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="chroma sqlite 路径，用于剔除库中不存在的期望论文")
    parser.add_argument("--collection", default=os.environ.get("PIXIU_RAG_COLLECTION", DEFAULT_COLLECTION))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    fixtures = load_fixtures(args.fixtures)
    papers = fixtures.get("papers") or []
    available = corpus_labels(args.db_path, args.collection, papers)

    print("=" * 78)
    print("检索质量基准 · 跨语言召回 / 坍缩度 / BM25 补召回")
    print("=" * 78)
    print(f"  端点      : {args.base_url}/api/rag/retrieve")
    print(f"  库内论文  : {sorted(available) if available else '未能读取（不剔除任何 case）'}")

    print("\n  --- 中文查询（走产品实际路径，含查询改写）---")
    zh_records = run_cases(
        fixtures.get("chineseCases") or [], "query", papers, available, args.base_url, args.top_k, args.timeout
    )
    zh = score(zh_records)

    print("\n  --- 中文查询的英文等价句（跨语言上限对照）---")
    en_equiv_records = run_cases(
        fixtures.get("chineseCases") or [], "englishEquivalent", papers, available, args.base_url, args.top_k, args.timeout
    )
    en_equiv = score(en_equiv_records)

    print("\n  --- 纯英文术语查询 ---")
    en_records = run_cases(
        fixtures.get("englishCases") or [], "query", papers, available, args.base_url, args.top_k, args.timeout
    )
    en = score(en_records)

    def ratio(metric: dict[str, Any], key: str) -> str:
        return f"{metric[key]}/{metric['total']}" if metric["total"] else "n/a"

    print("\n" + "=" * 78)
    print("汇总")
    print("=" * 78)
    for name, metric in (("中文查询", zh), ("中文→英文等价句", en_equiv), ("纯英文查询", en)):
        print(
            f"  {name:16s} top1={ratio(metric, 'top1'):6s} 有效top1={ratio(metric, 'effectiveTop1'):6s} "
            f"top3={ratio(metric, 'top3'):6s} bm25非零={ratio(metric, 'bm25NonZero'):6s} 改写={ratio(metric, 'rewritten')}"
        )
        if metric["collapsed"]:
            print(
                f"      ⚠ 坍缩：top-1 有 {metric['collapseRatio']:.0%} 落在 {metric['collapseTarget']}，"
                f"疑似假阳性 {metric['suspectedFalsePositives']}"
            )

    payload = {
        "schemaVersion": "1.0",
        "measuredAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "endpoint": f"{args.base_url}/api/rag/retrieve",
        "collection": args.collection,
        "topK": args.top_k,
        "corpusLabels": sorted(available),
        "collapseRatioThreshold": COLLAPSE_RATIO,
        "metrics": {"chinese": zh, "chineseEnglishEquivalent": en_equiv, "english": en},
        "records": {"chinese": zh_records, "chineseEnglishEquivalent": en_equiv_records, "english": en_records},
        "baseline": fixtures.get("baseline"),
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  结果已写入 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
