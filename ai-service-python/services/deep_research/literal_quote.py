"""Recover original whitespace without rewriting or fuzzy matching evidence."""
import re


def original_quote_span(quote, original):
    if not isinstance(quote, str) or not isinstance(original, str) or not quote.strip():
        return None
    if quote in original:
        return quote
    words = quote.split()
    pattern = r'\s+'.join(re.escape(word) for word in words)
    matches = re.finditer(pattern, original)
    first = next(matches, None)
    if first is None or next(matches, None) is not None:
        return None
    return original[first.start():first.end()]
