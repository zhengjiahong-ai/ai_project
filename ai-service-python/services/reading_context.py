"""Selection-centered page context; no retrieval, model calls or persistence."""

import re


def focus_page_context(page_text, selected_text, max_chars=3000):
    text = str(page_text or '').strip()
    if len(text) <= max_chars:
        return text
    term = ' '.join(str(selected_text or '').split())
    anchor = text.find(term) if term else -1
    if anchor < 0 and term:
        anchor = text.lower().find(term.lower())
    if anchor < 0 and term:
        match = re.search(r'\s+'.join(re.escape(word) for word in term.split()), text, re.IGNORECASE)
        anchor = match.start() if match else -1
    start = max(0, min(len(text) - max_chars, anchor - min(600, max_chars // 4) if anchor >= 0 else 0))
    return text[start:start + max_chars].strip()
