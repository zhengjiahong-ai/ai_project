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
        results = get_hybrid().retrieve(query, top_k=top_k)
    except Exception:
        results = {
            "vector": get_rag().retrieve(query, top_k=top_k, filter_metadata=filter_metadata),
            "bm25": [],
        }

    return {"status": "success", "query": query, "results": results}
