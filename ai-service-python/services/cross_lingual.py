"""Cross-lingual research synthesis — translate and integrate non-English papers.

Supports: zh (Chinese), ja (Japanese), de (German), fr (French), ko (Korean), es (Spanish).
Uses the translation LLM (DeepSeek flash) for fast, cost-effective translation.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

LANG_MAP = {
    "zh": "Chinese", "ja": "Japanese", "de": "German",
    "fr": "French", "ko": "Korean", "es": "Spanish",
    "en": "English",
}
TRANSLATE_TIMEOUT = 20


# ── Public API ───────────────────────────────────────────────────────────────

def cross_lingual_search(
    query: str,
    languages: list[str] | None = None,
    limit_per_lang: int = 5,
) -> dict[str, Any]:
    """Search for *query* across multiple languages.

    1. Translate query into each target language
    2. Search external academic providers in each language
    3. Translate results back to Chinese
    4. Deduplicate and merge

    Returns ``{status, query, translations, results, error}``.
    """
    if not query or not query.strip():
        return _error("Query cannot be empty.")
    languages = languages or ["zh", "en", "ja", "de"]
    languages = [l for l in languages if l in LANG_MAP]
    if "en" not in languages:
        languages.insert(0, "en")  # always include English

    query = query.strip()[:300]
    translations = _translate_query(query, languages)

    # Search per language
    all_results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for lang, translated_query in translations.items():
        if lang == "en":
            results = _search_academic(translated_query, limit_per_lang)
        else:
            raw = _search_academic(translated_query, limit_per_lang)
            results = _translate_results(raw, lang, query)

        for r in results:
            rid = r.get("providerId") or r.get("title", "")
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                r["sourceLanguage"] = lang
                all_results.append(r)

    return {
        "status": "success",
        "query": query,
        "translations": translations,
        "results": all_results[:30],
        "resultCount": len(all_results[:30]),
        "languagesSearched": list(translations.keys()),
        "error": "",
    }


def translate_text(text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
    """Translate *text* to *target_lang* using the translation LLM."""
    if not text or not text.strip():
        return ""
    try:
        from llm.client import get_translation_llm

        prompt = (
            f"Translate the following {LANG_MAP.get(source_lang, '')} text to "
            f"{LANG_MAP.get(target_lang, target_lang)}. "
            f"Preserve academic terminology and proper nouns. "
            f"Output only the translation, no explanations.\n\n{text[:2000]}"
        )

        def _call():
            return get_translation_llm()._call(prompt=prompt)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            return (future.result(timeout=TRANSLATE_TIMEOUT) or text)[:2000]
    except Exception:
        return text[:500]


# ── Internal ─────────────────────────────────────────────────────────────────

def _translate_query(query: str, languages: list[str]) -> dict[str, str]:
    result = {"en": query}
    for lang in languages:
        if lang == "en":
            continue
        result[lang] = translate_text(query, source_lang="auto", target_lang=lang)
    return result


def _search_academic(query: str, limit: int) -> list[dict[str, Any]]:
    try:
        from services.tool_registry import get_tool_registry
        registry = get_tool_registry()
        resp = registry.invoke("retrieve_external_academic", {"query": query, "limit": limit})
        return resp.get("items") or []
    except Exception:
        return []


def _translate_results(
    results: list[dict[str, Any]], source_lang: str, original_query: str,
) -> list[dict[str, Any]]:
    translated = []
    for r in results:
        try:
            if r.get("title"):
                r["title"] = translate_text(r["title"], source_lang, "zh")
            if r.get("abstract"):
                r["abstract"] = translate_text(r["abstract"][:1000], source_lang, "zh")
        except Exception:
            pass
        translated.append(r)
    return translated


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "query": "", "translations": {}, "results": [],
            "resultCount": 0, "languagesSearched": [], "error": message}
