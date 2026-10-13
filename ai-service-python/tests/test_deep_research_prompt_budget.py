"""Behavioural tests for prompt_budget.fit_evidence_prompt."""

from __future__ import annotations

import copy
import json

import pytest

from services.deep_research.prompt_budget import fit_evidence_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_render(rows: list[dict]) -> str:
    parts = ["INSTRUCTIONS: Summarize the evidence below."]
    for row in rows:
        parts.append(f"Q: {row.get('quote', '')}")
        ctx = row.get("sourceContext")
        if ctx:
            parts.append(f"CTX: {json.dumps(ctx, ensure_ascii=False)}")
    return "\n".join(parts)


def _quote_only_render(rows: list[dict]) -> str:
    return "".join(r.get("quote", "") for r in rows)


def _dict_map_render(rows: list[dict]) -> str:
    """Serialize rows as a JSON object keyed by positional index."""
    data = {str(i): row for i, row in enumerate(rows)}
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_max_bytes_bool_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            fit_evidence_prompt([], _simple_render, max_bytes=True)

    def test_max_bytes_zero_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            fit_evidence_prompt([], _simple_render, max_bytes=0)

    def test_max_bytes_negative_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            fit_evidence_prompt([], _simple_render, max_bytes=-5)

    def test_max_bytes_float_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            fit_evidence_prompt([], _simple_render, max_bytes=100.0)

    def test_max_bytes_string_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            fit_evidence_prompt([], _simple_render, max_bytes="500")

    def test_rows_not_list_rejected(self):
        with pytest.raises(ValueError, match="list of dicts"):
            fit_evidence_prompt("nope", _simple_render)

    def test_rows_non_dict_element_rejected(self):
        with pytest.raises(ValueError, match="list of dicts"):
            fit_evidence_prompt([{"quote": "a"}, 42], _simple_render)

    def test_render_non_string_output_rejected(self):
        with pytest.raises(ValueError, match="render must return a string"):
            fit_evidence_prompt([], lambda _rows: 12345)

    def test_render_none_output_rejected(self):
        with pytest.raises(ValueError, match="render must return a string"):
            fit_evidence_prompt([], lambda _rows: None)


# ---------------------------------------------------------------------------
# Fixed-content budget
# ---------------------------------------------------------------------------

class TestFixedContentTooLarge:
    def test_instructions_alone_exceed_budget(self):
        def big_render(_rows):
            return "X" * 200

        with pytest.raises(ValueError, match="prompt_fixed_content_too_large"):
            fit_evidence_prompt([], big_render, max_bytes=100)

    def test_instructions_at_exact_limit_ok(self):
        def render(_rows):
            return "AB"

        prompt, selected = fit_evidence_prompt([], render, max_bytes=2)
        assert prompt == "AB"
        assert selected == []


# ---------------------------------------------------------------------------
# Unicode byte accounting
# ---------------------------------------------------------------------------

class TestUnicodeByteLimits:
    def test_emoji_four_bytes_each(self):
        row = {"quote": "\U0001F525" * 10}  # 40 UTF-8 bytes
        prompt, sel = fit_evidence_prompt([row], _quote_only_render, max_bytes=40)
        assert len(sel) == 1
        assert prompt == "\U0001F525" * 10

        prompt, sel = fit_evidence_prompt([row], _quote_only_render, max_bytes=39)
        assert len(sel) == 0

    def test_cjk_three_bytes_each(self):
        row = {"quote": "\u6f22\u5b57" * 5}  # 30 bytes
        prompt, sel = fit_evidence_prompt([row], _quote_only_render, max_bytes=30)
        assert len(sel) == 1

        prompt, sel = fit_evidence_prompt([row], _quote_only_render, max_bytes=29)
        assert len(sel) == 0

    def test_mixed_ascii_and_multibyte(self):
        row = {"quote": "A\u00e9\u4e16"}  # 1 + 2 + 3 = 6 bytes
        prompt, sel = fit_evidence_prompt([row], _quote_only_render, max_bytes=6)
        assert len(sel) == 1

        prompt, sel = fit_evidence_prompt([row], _quote_only_render, max_bytes=5)
        assert len(sel) == 0


# ---------------------------------------------------------------------------
# No quote truncation
# ---------------------------------------------------------------------------

class TestNoQuoteTruncation:
    def test_oversized_row_skipped_entirely(self):
        long_quote = "B" * 500
        rows = [{"id": 1, "quote": long_quote}]
        prompt, sel = fit_evidence_prompt(rows, _quote_only_render, max_bytes=100)
        assert sel == []
        assert prompt == ""
        # Original untouched
        assert rows[0]["quote"] == long_quote

    def test_returned_quotes_match_originals(self):
        rows = [{"quote": "short"}, {"quote": "also short"}]
        prompt, sel = fit_evidence_prompt(rows, _quote_only_render, max_bytes=5000)
        assert [r["quote"] for r in sel] == ["short", "also short"]


# ---------------------------------------------------------------------------
# Skipping a huge row while retaining later short rows
# ---------------------------------------------------------------------------

class TestSkippingHugeRow:
    def test_huge_first_row_skipped_short_later_rows_kept(self):
        huge = {"id": 1, "quote": "X" * 1000}
        short_a = {"id": 2, "quote": "hi"}
        short_b = {"id": 3, "quote": "yo"}
        rows = [huge, short_a, short_b]

        prompt, sel = fit_evidence_prompt(rows, _quote_only_render, max_bytes=10)
        assert len(sel) == 2
        assert sel[0]["id"] == 2
        assert sel[1]["id"] == 3
        assert "X" not in prompt

    def test_middle_huge_row_skipped(self):
        rows = [
            {"id": 1, "quote": "aa"},
            {"id": 2, "quote": "Z" * 900},
            {"id": 3, "quote": "bb"},
        ]
        prompt, sel = fit_evidence_prompt(rows, _quote_only_render, max_bytes=8)
        ids = [r["id"] for r in sel]
        assert 1 in ids
        assert 3 in ids
        assert 2 not in ids


# ---------------------------------------------------------------------------
# Omitted-context marker
# ---------------------------------------------------------------------------

class TestOmittedContextMarker:
    def test_marker_present_when_context_stripped(self):
        ctx = {"url": "https://example.com", "page": 7}
        row = {"id": 1, "quote": "ev", "sourceContext": ctx}

        # Budget: fits stripped row but not full row with context.
        stripped_prompt = _simple_render([{"id": 1, "quote": "ev", "sourceContext": {}, "contextOmitted": True}])
        budget = len(stripped_prompt.encode("utf-8")) + 2

        prompt, sel = fit_evidence_prompt([row], _simple_render, max_bytes=budget)
        assert len(sel) == 1
        assert sel[0]["contextOmitted"] is True
        assert sel[0]["sourceContext"] == {}
        assert sel[0]["quote"] == "ev"
        assert sel[0]["id"] == 1

    def test_no_marker_when_context_absent(self):
        row = {"id": 1, "quote": "ev"}
        prompt, sel = fit_evidence_prompt([row], _simple_render, max_bytes=5000)
        assert "contextOmitted" not in sel[0]

    def test_no_marker_when_context_empty_dict(self):
        row = {"id": 1, "quote": "ev", "sourceContext": {}}
        prompt, sel = fit_evidence_prompt([row], _simple_render, max_bytes=5000)
        assert "contextOmitted" not in sel[0]


# ---------------------------------------------------------------------------
# Context restoration
# ---------------------------------------------------------------------------

class TestRestoration:
    def test_context_restored_when_budget_allows(self):
        ctx = {"url": "https://x.io"}
        row = {"id": 1, "quote": "hi", "sourceContext": ctx}
        prompt, sel = fit_evidence_prompt([row], _simple_render, max_bytes=50000)
        assert sel[0]["sourceContext"] == ctx
        assert "contextOmitted" not in sel[0]

    def test_partial_restoration_order(self):
        """First row context restored; second stays omitted when tight."""
        ctx_a = {"src": "a"}
        ctx_b = {"src": "b" * 200}  # large context
        rows = [
            {"id": 1, "quote": "q1", "sourceContext": ctx_a},
            {"id": 2, "quote": "q2", "sourceContext": ctx_b},
        ]
        # Budget: fits both stripped + first context but not second context.
        stripped = [
            {"id": 1, "quote": "q1", "sourceContext": {}, "contextOmitted": True},
            {"id": 2, "quote": "q2", "sourceContext": {}, "contextOmitted": True},
        ]
        with_first = [
            {"id": 1, "quote": "q1", "sourceContext": ctx_a},
            {"id": 2, "quote": "q2", "sourceContext": {}, "contextOmitted": True},
        ]
        budget = len(_simple_render(with_first).encode("utf-8")) + 1

        prompt, sel = fit_evidence_prompt(rows, _simple_render, max_bytes=budget)
        assert len(sel) == 2
        assert sel[0]["sourceContext"] == ctx_a
        assert "contextOmitted" not in sel[0]
        assert sel[1]["sourceContext"] == {}
        assert sel[1]["contextOmitted"] is True


# ---------------------------------------------------------------------------
# No mutation of inputs
# ---------------------------------------------------------------------------

class TestNoMutation:
    def test_rows_not_mutated(self):
        ctx = {"key": "value", "nested": [1, 2]}
        rows = [
            {"id": 1, "quote": "hello", "sourceContext": ctx},
            {"id": 2, "quote": "world"},
        ]
        snapshot = copy.deepcopy(rows)
        budget = len(_simple_render([rows[1]]).encode("utf-8"))
        _, selected = fit_evidence_prompt(rows, _simple_render, max_bytes=budget)
        assert selected == [{"id": 1, "quote": "hello", "sourceContext": {}, "contextOmitted": True}]
        assert rows == snapshot
        assert rows[0]["sourceContext"] is ctx

    def test_rows_not_mutated_on_full_fit(self):
        rows = [{"id": 1, "quote": "ok", "sourceContext": {"a": 1}}]
        snapshot = copy.deepcopy(rows)
        fit_evidence_prompt(rows, _simple_render, max_bytes=99999)
        assert rows == snapshot


# ---------------------------------------------------------------------------
# Exact boundary
# ---------------------------------------------------------------------------

class TestExactBoundary:
    def test_prompt_exactly_max_bytes(self):
        row = {"quote": "AB"}  # 2 bytes
        prompt, sel = fit_evidence_prompt([row], _quote_only_render, max_bytes=2)
        assert sel == [row]
        assert prompt == "AB"

    def test_one_byte_over_rejected(self):
        row = {"quote": "AB"}
        prompt, sel = fit_evidence_prompt([row], _quote_only_render, max_bytes=1)
        assert sel == []

    def test_multibyte_boundary(self):
        row = {"quote": "\u00e9"}  # 2 bytes
        prompt, sel = fit_evidence_prompt([row], _quote_only_render, max_bytes=2)
        assert len(sel) == 1
        prompt, sel = fit_evidence_prompt([row], _quote_only_render, max_bytes=1)
        assert len(sel) == 0


# ---------------------------------------------------------------------------
# Dict/map serialization render (not list JSON)
# ---------------------------------------------------------------------------

class TestDictMapSerialization:
    def test_all_rows_fit(self):
        rows = [
            {"id": 1, "quote": "alpha"},
            {"id": 2, "quote": "beta"},
        ]
        prompt, sel = fit_evidence_prompt(rows, _dict_map_render, max_bytes=50000)
        assert len(sel) == 2
        parsed = json.loads(prompt)
        assert parsed["0"]["quote"] == "alpha"
        assert parsed["1"]["quote"] == "beta"

    def test_oversized_row_skipped_with_dict_render(self):
        rows = [
            {"id": 1, "quote": "Z" * 500},
            {"id": 2, "quote": "ok"},
        ]
        short_only = _dict_map_render([{"id": 2, "quote": "ok"}])
        budget = len(short_only.encode("utf-8")) + 2

        prompt, sel = fit_evidence_prompt(rows, _dict_map_render, max_bytes=budget)
        assert len(sel) == 1
        assert sel[0]["quote"] == "ok"
        parsed = json.loads(prompt)
        assert "0" in parsed
        assert parsed["0"]["quote"] == "ok"


# ---------------------------------------------------------------------------
# Empty rows edge case
# ---------------------------------------------------------------------------

class TestEmptyRows:
    def test_empty_rows_returns_empty_prompt_and_list(self):
        def render(r):
            return ""

        prompt, sel = fit_evidence_prompt([], render, max_bytes=10)
        assert prompt == ""
        assert sel == []
