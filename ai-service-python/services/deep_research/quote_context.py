"""Context extraction around a literal quote for deep-research evidence.

This helper supplies *context only*.  It treats every string as raw text:
it never infers entities, never normalizes whitespace, and never invents
text.  Its job is to hand a reviewer (or a downstream verifier) the
sentences surrounding a quoted span so that antecedents such as a
previously named subject, a contrast, or an "it" attribution survive even
when they sit hundreds of characters away from the quote itself.

Segmentation rules (single linear scan):

* Chinese / full-width terminators (。！？!？) always end a sentence.
* ASCII ``.`` / ``?`` / ``!`` end a sentence only when followed by
  whitespace or end of text (so ``3.14`` does not split).
* Newlines alone are NOT boundaries (PDF line wraps).

``before`` retains up to the three preceding non-empty sentence segments;
``after`` up to the two following non-empty sentence segments.  Each side
is additionally hard-capped at ``max(window, 1000)`` characters, where
``window`` is clamped to ``0..2000`` and falls back to the default of 240
when invalid or a bool.  ``truncated`` is True iff any text outside
``before + quote + after`` was omitted.
"""

from __future__ import annotations

import math

__all__ = ["quote_context"]

_DEFAULT_WINDOW = 240
_MIN_WINDOW = 0
_MAX_WINDOW = 2000
_SIDE_FLOOR = 1000
_MAX_BEFORE_SEGMENTS = 3
_MAX_AFTER_SEGMENTS = 2

# 。！？!？ — CJK / full-width terminators end a sentence unconditionally.
_CJK_TERMINALS = "。！？"
_ASCII_TERMINALS = ".?!"


def _normalize_window(window):
    """Clamp ``window`` to 0..2000; bools and invalid values -> 240."""
    if isinstance(window, bool):
        return _DEFAULT_WINDOW
    if isinstance(window, int):
        value = window
    elif isinstance(window, float):
        if not math.isfinite(window):
            return _DEFAULT_WINDOW
        value = int(window)
    else:
        return _DEFAULT_WINDOW
    if value < _MIN_WINDOW:
        return _MIN_WINDOW
    if value > _MAX_WINDOW:
        return _MAX_WINDOW
    return value


def _sentence_cuts(text):
    """Return indices one past each sentence terminator (O(n) scan)."""
    cuts = []
    length = len(text)
    for index, char in enumerate(text):
        if char in _CJK_TERMINALS:
            cuts.append(index + 1)
        elif char in _ASCII_TERMINALS:
            nxt = index + 1
            if nxt == length or text[nxt].isspace():
                cuts.append(nxt)
    return cuts


def quote_context(evidence, window=_DEFAULT_WINDOW):
    """Return sentence context around the FIRST literal quote occurrence.

    ``evidence`` must be a dict carrying string ``sourceContext`` and
    ``quote`` entries.  Returns ``{}`` for malformed evidence, an empty
    quote, or a quote that is not a literal substring of ``sourceContext``.

    The result dict holds ``before``, ``after``, and
    ``truncated``.  ``before`` / ``after`` are exact contiguous slices of
    ``sourceContext`` around the first literal occurrence of ``quote``;
    original characters and newlines are preserved verbatim, nothing is
    normalized, and the quote span itself is never duplicated in the
    returned slices at its occurrence.
    """
    if not isinstance(evidence, dict):
        return {}
    source = evidence.get("sourceContext")
    quote = evidence.get("quote")
    if not isinstance(source, str) or not isinstance(quote, str):
        return {}
    if not quote:
        return {}
    start = source.find(quote)
    if start == -1:
        return {}
    end = start + len(quote)

    cap = max(_normalize_window(window), _SIDE_FLOOR)
    cuts = _sentence_cuts(source)

    # --- before: up to 3 preceding non-empty sentence segments ---
    bounds = [0]
    for cut in cuts:
        if cut > start:
            break
        bounds.append(cut)
    if bounds[-1] != start:
        bounds.append(start)

    keep_from = len(bounds) - 1
    seen = 0
    for seg_index in range(len(bounds) - 2, -1, -1):
        if source[bounds[seg_index]:bounds[seg_index + 1]].strip():
            keep_from = seg_index
            seen += 1
            if seen >= _MAX_BEFORE_SEGMENTS:
                break
    before_full = source[bounds[keep_from]:start]
    before = before_full[-cap:] if len(before_full) > cap else before_full

    # --- after: up to 2 following non-empty sentence segments ---
    bounds_a = [end]
    for cut in cuts:
        if cut >= end:
            bounds_a.append(cut)
    if bounds_a[-1] != len(source):
        bounds_a.append(len(source))

    keep_to = 0
    seen = 0
    for seg_index in range(len(bounds_a) - 1):
        if source[bounds_a[seg_index]:bounds_a[seg_index + 1]].strip():
            seen += 1
            keep_to = seg_index + 1
            if seen >= _MAX_AFTER_SEGMENTS:
                break
    after_full = source[end:bounds_a[keep_to]]
    after = after_full[:cap]

    truncated = start > len(before) or (len(source) - end) > len(after)
    return {
        "before": before,
        "after": after,
        "truncated": truncated,
    }
