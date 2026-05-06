import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List

from llm.client import get_translation_llm
from schemas.requests import PageTranslationRequest

STRUCTURED_MAX_BLOCKS_PER_BATCH = 8
STRUCTURED_MAX_CHARS_PER_BATCH = 1000
STRUCTURED_BATCH_TIMEOUT_SECONDS = 60
STRUCTURED_BATCH_WORKERS = 3
PLAIN_TRANSLATION_TIMEOUT_SECONDS = 90
STRUCTURED_SINGLE_BLOCK_TIMEOUT_SECONDS = 20
STRUCTURED_INDIVIDUAL_RETRY_LIMIT = 4
STRUCTURED_INDIVIDUAL_RETRY_WORKERS = 4


def _stringify_paper_skeleton(paper_skeleton: Dict[str, Any] | None) -> str:
    if not paper_skeleton:
        return "暂无可用的论文结构摘要。"

    return "\n".join(f"- {section}: {summary}" for section, summary in paper_skeleton.items())


def _trim_page_text(page_text: str, max_chars: int = 12000) -> str:
    text = (page_text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[内容过长，已截断后翻译]"


def _trim_translation_reference(paper_skeleton: Dict[str, Any] | None, max_chars: int = 1200) -> str:
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


def _normalize_layout_blocks(page_layout: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    blocks = page_layout.get("blocks") if isinstance(page_layout, dict) else []
    normalized: List[Dict[str, Any]] = []

    for index, block in enumerate(blocks or []):
        block_id = str(block.get("id") or f"block-{index + 1}").strip()
        text = str(block.get("text") or "").strip()
        if not block_id or not text:
            continue

        normalized.append(
            {
                "id": block_id,
                "text": text,
                "style": block.get("style") or {},
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

论文结构摘要（仅供术语参考）：
{skeleton_text}

当前页码（从 1 开始）：
{page_index + 1}

当前页原文：
{trimmed_page_text}
"""


def _build_structured_translation_prompt(page_index: int, skeleton_text: str, blocks: List[Dict[str, Any]]) -> str:
    block_payload = json.dumps(
        [{"id": block["id"], "text": block["text"], "style": block.get("style") or {}} for block in blocks],
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


def _normalize_translated_blocks(payload: Any, source_blocks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    if isinstance(payload, dict):
        candidate_blocks = payload.get("translatedBlocks")
    elif isinstance(payload, list):
        candidate_blocks = payload
    else:
        candidate_blocks = []

    if not isinstance(candidate_blocks, list):
        return []

    source_by_id = {block["id"]: block for block in source_blocks}
    translated_by_id: Dict[str, str] = {}

    for item in candidate_blocks:
        block_id = str(item.get("id") or "").strip()
        translated_text = str(item.get("translatedText") or "").strip()
        if not block_id or not translated_text or block_id not in source_by_id:
            continue
        translated_by_id[block_id] = translated_text

    return [
        {"id": block["id"], "translatedText": translated_by_id[block["id"]]}
        for block in source_blocks
        if block["id"] in translated_by_id
    ]


def _chunk_layout_blocks(
    blocks: List[Dict[str, Any]],
    max_blocks: int = STRUCTURED_MAX_BLOCKS_PER_BATCH,
    max_chars: int = STRUCTURED_MAX_CHARS_PER_BATCH,
) -> List[List[Dict[str, Any]]]:
    batches: List[List[Dict[str, Any]]] = []
    current_batch: List[Dict[str, Any]] = []
    current_chars = 0

    for block in blocks:
        block_chars = len(block["text"])
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


def _translate_block_batch(page_index: int, skeleton_text: str, blocks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    prompt = _build_structured_translation_prompt(page_index, skeleton_text, blocks)
    raw_response = _call_translation_with_timeout(prompt, timeout_seconds=STRUCTURED_BATCH_TIMEOUT_SECONDS)
    payload = _extract_json_payload(raw_response)
    return _normalize_translated_blocks(payload, blocks)


def _build_single_block_translation_prompt(page_index: int, skeleton_text: str, block: Dict[str, Any]) -> str:
    return f"""Translate one PDF text box into Simplified Chinese.

Rules:
- Return only the translated text for this one box.
- Do not add labels, quotes, markdown fences, explanations, or JSON.
- Preserve citation numbers, equations, code identifiers, emails, and proper nouns when appropriate.
- Keep the result concise because it will be rendered back into the original PDF text box.

Paper context:
{skeleton_text}

Page: {page_index + 1}
Block id: {block["id"]}
Text:
{block["text"]}
"""


def _clean_single_block_translation(raw_text: str) -> str:
    cleaned = (raw_text or "").strip()
    cleaned = re.sub(r"^```(?:text|markdown)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()

    return cleaned


def _translate_single_block(page_index: int, skeleton_text: str, block: Dict[str, Any]) -> Dict[str, str] | None:
    prompt = _build_single_block_translation_prompt(page_index, skeleton_text, block)
    translated_text = _clean_single_block_translation(
        _call_translation_with_timeout(prompt, timeout_seconds=STRUCTURED_SINGLE_BLOCK_TIMEOUT_SECONDS)
    )
    if not translated_text:
        return None
    return {"id": block["id"], "translatedText": translated_text}


def _translate_missing_blocks_individually(
    page_index: int,
    skeleton_text: str,
    missing_blocks: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    if not missing_blocks or len(missing_blocks) > STRUCTURED_INDIVIDUAL_RETRY_LIMIT:
        return []

    def translate_one(block: Dict[str, Any]) -> Dict[str, str] | None:
        try:
            return _translate_single_block(page_index, skeleton_text, block)
        except Exception as error:
            print(f"Structured translation single-block retry failed for {block['id']}: {error}")
            return None

    max_workers = min(STRUCTURED_INDIVIDUAL_RETRY_WORKERS, len(missing_blocks))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return [result for result in executor.map(translate_one, missing_blocks) if result]


def _translate_blocks(
    page_index: int,
    skeleton_text: str,
    page_layout: Dict[str, Any] | None,
) -> List[Dict[str, str]]:
    blocks = _normalize_layout_blocks(page_layout)
    if not blocks:
        return []

    translated_blocks: List[Dict[str, str]] = []
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
                print(f"Structured translation batch failed, continuing with remaining batches: {error}")

    minimum_expected = max(1, len(blocks) // 2)
    translated_by_id = {block["id"]: block for block in translated_blocks}
    if len(translated_by_id) < minimum_expected:
        missing_blocks = [block for block in blocks if block["id"] not in translated_by_id]
        if len(missing_blocks) <= STRUCTURED_INDIVIDUAL_RETRY_LIMIT:
            for translated_block in _translate_missing_blocks_individually(page_index, skeleton_text, missing_blocks):
                translated_by_id[translated_block["id"]] = translated_block

    ordered_translated_blocks = [
        {"id": block["id"], "translatedText": translated_by_id[block["id"]]["translatedText"]}
        for block in blocks
        if block["id"] in translated_by_id
    ]

    return ordered_translated_blocks if len(ordered_translated_blocks) >= minimum_expected else []


def translate_page(request: PageTranslationRequest) -> Dict[str, Any]:
    page_text = (request.pageText or "").strip()
    if not page_text:
        raise ValueError("Page text cannot be empty.")

    page_index = max(0, int(request.pageIndex or 0))
    paper_skeleton = request.paperSkeleton or {}
    skeleton_text = _trim_translation_reference(paper_skeleton)
    page_layout = request.pageLayout or {}

    try:
        translated_blocks = _translate_blocks(page_index, skeleton_text, page_layout)
    except Exception as error:
        print(f"Structured translation failed, falling back to plain mode: {error}")
        translated_blocks = []

    if translated_blocks:
        translated_text = "\n\n".join(block["translatedText"] for block in translated_blocks).strip()
        return {
            "status": "success",
            "pageIndex": page_index,
            "sourceText": page_text,
            "translatedText": translated_text,
            "translatedBlocks": translated_blocks,
            "renderMode": "overlay",
        }

    trimmed_page_text = _trim_page_text(page_text)
    prompt = _build_plain_translation_prompt(page_index, skeleton_text, trimmed_page_text)
    translated_text = _call_translation_with_timeout(prompt, timeout_seconds=PLAIN_TRANSLATION_TIMEOUT_SECONDS).strip()
    if not translated_text:
        raise RuntimeError("Translation model returned empty content.")

    return {
        "status": "success",
        "pageIndex": page_index,
        "sourceText": page_text,
        "translatedText": translated_text,
        "translatedBlocks": [],
        "renderMode": "plain",
    }
