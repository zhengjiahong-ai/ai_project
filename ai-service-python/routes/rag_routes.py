import json

try:
    from fastapi import APIRouter, File, UploadFile
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - test-only fallback
    from tests.fastapi_stubs import (
        APIRouter,
        File,
        JSONResponse,
        UploadFile,
    )

from services import rag_service

rag_router = APIRouter()


def _parse_json_object(raw: str | None, field: str) -> dict | None:
    """把 JSON 字符串形式的对象参数解析成 dict。

    FastAPI 不能把 `dict | None` 当查询参数：它会把这个参数从 OpenAPI 里整个丢掉，
    并且无论客户端传什么都恒传 None。实测 `/rag/retrieve` 传一个不存在的 pdf id，
    返回结果与完全不传过滤条件一模一样，过滤被静默跳过。
    因此这里改用 JSON 字符串，并且解析失败必须报 400 —— 静默忽略正是原缺陷最
    难发现的地方。
    """
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"{field} must be a JSON object: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{field} must be a JSON object")
    return parsed or None


@rag_router.post("/rag/add-literature")
async def rag_add_literature(file: UploadFile = File(...), metadata: str | None = None):
    try:
        extra_metadata = _parse_json_object(metadata, "metadata")
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=400)

    try:
        return JSONResponse(await rag_service.add_literature(file, extra_metadata))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@rag_router.post("/rag/retrieve")
async def rag_retrieve(
    query: str,
    top_k: int = 5,
    pdf_id: str | None = None,
    filter_metadata: str | None = None,
):
    """混合检索，返回 vector / bm25 / fused 三路结果。

    过滤有两种写法，可同时使用（pdf_id 覆盖 filter_metadata 里的 id）：
    - `pdf_id=xxx`：只在这一篇论文里检索，最常用的场景；
    - `filter_metadata={"section_title": "..."}`：任意 metadata 等值过滤，JSON 字符串。
    """
    try:
        where = _parse_json_object(filter_metadata, "filter_metadata")
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=400)

    if pdf_id:
        where = {**(where or {}), "id": pdf_id}

    try:
        return JSONResponse(rag_service.retrieve(query, top_k=top_k, filter_metadata=where))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)
