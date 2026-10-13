import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

_logger = logging.getLogger(__name__)

from llm.client import get_translation_llm
from schemas.requests import PageTranslationRequest
from services.translation_math import (SCOPE_POLICY, protect_inline_math, has_intact_math_tokens,
                                       visible_math_context, has_unsafe_subtraction_scope)

STRUCTURED_MAX_BLOCKS_PER_BATCH = 8
STRUCTURED_MAX_CHARS_PER_BATCH = 1000
STRUCTURED_BATCH_TIMEOUT_SECONDS = 60
STRUCTURED_BATCH_WORKERS = 3
PLAIN_TRANSLATION_TIMEOUT_SECONDS = 90


def _stringify_paper_skeleton(paper_skeleton: dict[str, Any] | None) -> str:
    if not paper_skeleton:
        return "暂无可用的论文结构摘要。"

    return "\n".join(f"- {section}: {summary}" for section, summary in paper_skeleton.items())


def _trim_page_text(page_text: str, max_chars: int = 12000) -> str:
    text = (page_text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[内容过长，已截断后翻译]"


def _trim_translation_reference(paper_skeleton: dict[str, Any] | None, max_chars: int = 1200) -> str:
    reference = _stringify_paper_skeleton(paper_skeleton)
    if len(reference) <= max_chars:
        return reference
    return reference[:max_chars].rstrip() + "\n..."


def _call_translation_with_timeout(prompt: str, timeout_seconds: int = 45) -> str:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(get_translation_llm()._call, prompt)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError as error:
        future.cancel()
        raise RuntimeError(f"Translation timed out after {timeout_seconds} seconds.") from error
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _extract_json_payload(text: str) -> Any:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalize_layout_blocks(page_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    blocks = page_layout.get("blocks") if isinstance(page_layout, dict) else []
    normalized: list[dict[str, Any]] = []
    math_index = 0

    for index, block in enumerate(blocks or []):
        block_id = str(block.get("id") or f"block-{index + 1}").strip()
        text = str(block.get("text") or "").strip()
        if not block_id or not text:
            continue

        protected = protect_inline_math(text, math_index)
        math_index = max([math_index, *[int(value) for value in re.findall(r'⟦原式(\d+)⟧', protected)]])
        normalized.append(
            {
                "id": block_id,
                "text": protected,
                "style": block.get("style") or {},
                "mathContext": visible_math_context(protected, block.get('mathSources')),
            }
        )

    return normalized


def _build_plain_translation_prompt(page_index: int, skeleton_text: str, trimmed_page_text: str) -> str:
    return f"""你是一位严谨的学术论文翻译助手。
请将下面这一页论文内容翻译成简体中文。

严格要求：
1. 只翻译原文已有内容，不补写、不总结、不解释。
2. 保留段落结构、列表层次、公式、缩写、引用编号。
3. 专有名词如无公认译法，可保留英文并在中文中自然嵌入。
4. 输出只包含译文正文，不要添加标题、说明、前言或结语。
5. 追求准确与直接，不要额外润色。
6. ⟦原式数字⟧是原图中保留的数学表达式，必须原样保留且每个出现一次；不要推测、展开、补写公式。
{SCOPE_POLICY}

论文结构摘要（仅供术语参考）：
{skeleton_text}

当前页码（从 1 开始）：
{page_index + 1}

当前页原文：
{trimmed_page_text}
"""


def _build_structured_translation_prompt(page_index: int, skeleton_text: str, blocks: list[dict[str, Any]]) -> str:
    block_payload = json.dumps(
        [{"id": block["id"], "text": block["text"], "style": block.get("style") or {},
          "mathContext": block.get('mathContext') or []} for block in blocks],
        ensure_ascii=False,
        indent=2,
    )
    return f"""你是一位严谨的学术论文翻译助手。
请将当前 PDF 页面的正文文本块逐块翻译成简体中文，并严格保持每个块的语义边界。

严格要求：
1. 只翻译给出的文本块，不补写、不总结、不解释。
2. 保留公式、缩写、引用编号、列表标记和术语的一致性。
3. 图表、表格、图题、表题和图内文字已经被前处理排除，不要自行补回。
4. 每个输入块都必须按原样返回相同的 id。
5. 输出严格 JSON，不要输出任何额外说明。
6. ⟦原式数字⟧标记必须原样保留且各出现一次；它们在原文图中显示，不能推测、展开、补写公式。
{SCOPE_POLICY}

JSON 格式：
{{
  "translatedBlocks": [
    {{
      "id": "block-1",
      "translatedText": "对应块的中文译文"
    }}
  ]
}}

论文结构摘要（仅供术语参考）：
{skeleton_text}

当前页码（从 1 开始）：
{page_index + 1}

待翻译文本块：
{block_payload}
"""


def _normalize_translated_blocks(payload: Any, source_blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    if isinstance(payload, dict):
        candidate_blocks = payload.get("translatedBlocks")
    elif isinstance(payload, list):
        candidate_blocks = payload
    else:
        candidate_blocks = []

    if not isinstance(candidate_blocks, list):
        return []

    source_by_id = {block["id"]: block for block in source_blocks}
    translated_by_id: dict[str, str] = {}

    for item in candidate_blocks:
        block_id = str(item.get("id") or "").strip()
        translated_text = str(item.get("translatedText") or "").strip()
        if not block_id or not translated_text or block_id not in source_by_id:
            continue
        if not has_intact_math_tokens(source_by_id[block_id]['text'], translated_text):
            continue
        if has_unsafe_subtraction_scope(source_by_id[block_id]['text'], translated_text):
            continue
        translated_by_id[block_id] = translated_text

    return [
        {"id": block["id"], "translatedText": translated_by_id[block["id"]]}
        for block in source_blocks
        if block["id"] in translated_by_id
    ]


def _chunk_layout_blocks(
    blocks: list[dict[str, Any]],
    max_blocks: int = STRUCTURED_MAX_BLOCKS_PER_BATCH,
    max_chars: int = STRUCTURED_MAX_CHARS_PER_BATCH,
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []
    current_chars = 0

    for block in blocks:
        context = block.get('mathContext') or []
        block_chars = len(block["text"]) + (len(json.dumps(context, ensure_ascii=False)) if context else 0)
        should_start_next_batch = (
            current_batch
            and (len(current_batch) >= max_blocks or current_chars + block_chars > max_chars)
        )

        if should_start_next_batch:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0

        current_batch.append(block)
        current_chars += block_chars

    if current_batch:
        batches.append(current_batch)

    return batches


def _translate_block_batch(page_index: int, skeleton_text: str, blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    prompt = _build_structured_translation_prompt(page_index, skeleton_text, blocks)
    raw_response = _call_translation_with_timeout(prompt, timeout_seconds=STRUCTURED_BATCH_TIMEOUT_SECONDS)
    payload = _extract_json_payload(raw_response)
    return _normalize_translated_blocks(payload, blocks)


def _translate_blocks(
    page_index: int,
    skeleton_text: str,
    page_layout: dict[str, Any] | None,
) -> list[dict[str, str]]:
    blocks = _normalize_layout_blocks(page_layout)
    if not blocks:
        return []

    translated_blocks: list[dict[str, str]] = []
    batches = _chunk_layout_blocks(blocks)
    max_workers = min(STRUCTURED_BATCH_WORKERS, len(batches))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_translate_block_batch, page_index, skeleton_text, batch)
            for batch in batches
        ]
        for future in futures:
            try:
                translated_blocks.extend(future.result())
            except Exception as error:
                _logger.warning("Structured translation batch failed, continuing with remaining batches: %s", error)

    translated_by_id = {block["id"]: block for block in translated_blocks}

    ordered_translated_blocks = [
        {"id": block["id"], "translatedText": translated_by_id[block["id"]]["translatedText"]}
        for block in blocks
        if block["id"] in translated_by_id
    ]

    return ordered_translated_blocks


def translate_page(request: PageTranslationRequest) -> dict[str, Any]:
    page_text = (request.pageText or "").strip()
    if not page_text:
        raise ValueError("Page text cannot be empty.")

    page_index = max(0, int(request.pageIndex or 0))
    paper_skeleton = request.paperSkeleton or {}
    skeleton_text = _trim_translation_reference(paper_skeleton)
    page_layout = request.pageLayout or {}

    source_blocks = _normalize_layout_blocks(page_layout)
    if source_blocks:
        translated_blocks = _translate_blocks(page_index, skeleton_text, page_layout)
        if not translated_blocks:
            raise RuntimeError("当前页段落翻译未完成，原文仍可阅读；请手动重试。")
        completed = {block['id'] for block in translated_blocks}
        missing = [block['id'] for block in source_blocks if block['id'] not in completed]
        translated_text = "\n\n".join(block["translatedText"] for block in translated_blocks).strip()
        return {
            "status": "partial" if missing else "success",
            "pageIndex": page_index,
            "sourceText": page_text,
            "translatedText": translated_text,
            "translatedBlocks": translated_blocks,
            "renderMode": "overlay",
            "missingBlockIds": missing,
            "warning": f"还有 {len(missing)} 个段落未完成，已保留当前译文；可手动重试。" if missing else "",
            "mathProtectionVersion": 2 if any(block.get('mathSources') for block in page_layout.get('blocks', [])) else 1,
        }

    trimmed_page_text = protect_inline_math(_trim_page_text(page_text))
    prompt = _build_plain_translation_prompt(page_index, skeleton_text, trimmed_page_text)
    translated_text = _call_translation_with_timeout(prompt, timeout_seconds=PLAIN_TRANSLATION_TIMEOUT_SECONDS).strip()
    if not translated_text:
        raise RuntimeError("Translation model returned empty content.")
    if not has_intact_math_tokens(trimmed_page_text, translated_text):
        raise RuntimeError("译文未完整保留原式标记，请查看原文；可手动重试。")
    if has_unsafe_subtraction_scope(trimmed_page_text, translated_text):
        raise RuntimeError('译文改变了原式的运算范围，请查看原文；可手动重试。')

    return {
        "status": "success",
        "pageIndex": page_index,
        "sourceText": page_text,
        "translatedText": translated_text,
        "translatedBlocks": [],
        "renderMode": "plain",
        "mathProtectionVersion": 1,
    }
