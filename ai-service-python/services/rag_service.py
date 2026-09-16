import os
import tempfile
from typing import Any

from fastapi import UploadFile

from rag.store import get_hybrid, get_rag


async def add_literature(file: UploadFile, metadata: dict | None = None) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
        temp_file.write(await file.read())
        temp_file_path = temp_file.name

    try:
        chunk_num = get_rag().add_literature_to_db(temp_file_path, metadata or {})
        return {
            "status": "success",
            "message": f"Indexed literature into {chunk_num} chunks.",
            "chunk_num": chunk_num,
            "total_chunks": get_rag().get_db_stats(),
        }
    finally:
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


def retrieve(query: str, top_k: int = 5, filter_metadata: dict | None = None) -> dict[str, Any]:
    try:
        # 旧实现把 filter_metadata 丢在这一行：调用方要求“只搜某篇论文”，实际搜了全库
        results = get_hybrid().retrieve(query, top_k=top_k, filter_metadata=filter_metadata)
    except Exception:
        results = {
            "vector": get_rag().retrieve(query, top_k=top_k, filter_metadata=filter_metadata),
            "bm25": [],
            "fused": [],
        }

    return {
        "status": "success",
        "query": query,
        # 中文查询会被改写成英文再检索（见 core/query_rewriter），把实际用的查询
        # 回给调用方，否则“问中文却返回英文片段”无从排查。
        "searchQuery": results.get("searchQuery", query),
        "queryRewritten": bool(results.get("queryRewritten")),
        "results": results,
    }
