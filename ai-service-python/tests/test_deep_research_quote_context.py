"""Tests for services/deep_research/quote_context.py (stdlib only)."""

import copy
from services.deep_research.quote_context import quote_context


def _ev(source, quote):
    return {"sourceContext": source, "quote": quote}


def test_preceding_subject_more_than_240_chars_away_across_two_sentences():
    subject = "Elena Vasquez first described the phenomenon. "
    filler = "x" * 260 + ". "
    lead_in = "The team concluded that "
    quote = "the effect is reproducible"
    source = subject + filler + lead_in + quote + " in every trial."
    result = quote_context(_ev(source, quote))
    assert result["before"] == subject + filler + lead_in
    assert len(result["before"]) > 240
    assert "Elena Vasquez" in result["before"]
    assert result["after"] == " in every trial."
    assert result["truncated"] is False


def test_contrast_and_it_attribution_context_retained():
    source = (
        "The original report blamed the scheduler. "
        "A rival team blamed the network fabric and published a rebuttal "
        "citing packet traces from two data centers. "
        'Critics said "it was misconfigured from the start" during review.'
    )
    quote = "it was misconfigured from the start"
    result = quote_context(_ev(source, quote))
    assert "scheduler" in result["before"]
    assert "rebuttal" in result["before"]
    assert result["before"].endswith('Critics said "')
    assert result["after"] == '" during review.'
    assert result["truncated"] is False


def test_quote_at_start_of_source():
    quote = "alpha beta"
    source = quote + " first tail. second tail. third tail."
    result = quote_context(_ev(source, quote))
    assert result["before"] == ""
    assert result["after"] == " first tail. second tail."
    assert result["truncated"] is True


def test_quote_at_end_of_source():
    quote = "final words"
    source = "one. two. " + quote
    result = quote_context(_ev(source, quote))
    assert result["before"] == "one. two. "
    assert result["after"] == ""
    assert result["truncated"] is False


def test_quote_is_entire_source():
    result = quote_context(_ev("only this", "only this"))
    assert result == {
        "before": "",
        "after": "",
        "truncated": False,
    }


def test_long_unbroken_sentence_respects_hard_cap():
    quote = "Q"
    source = "x" * 3000 + " " + quote
    result = quote_context(_ev(source, quote))
    assert len(result["before"]) == 1000
    assert result["before"] == "x" * 999 + " "
    assert result["after"] == ""
    assert result["truncated"] is True

    wide = quote_context(_ev(source, quote), window=2000)
    assert len(wide["before"]) == 2000
    assert wide["before"] == "x" * 1999 + " "
    assert wide["truncated"] is True


def test_ascii_terminal_requires_trailing_whitespace():
    quote = "Q"
    source = "one. two. three. v1.2 four Q"
    result = quote_context(_ev(source, quote))
    assert result["before"] == " two. three. v1.2 four "
    assert "one." not in result["before"]
    assert "v1.2" in result["before"]
    assert result["truncated"] is True


def test_newlines_alone_are_not_sentence_boundaries():
    quote = "Q"
    source = "s1. s2. s3. alpha\nbeta Q"
    result = quote_context(_ev(source, quote))
    assert result["before"] == " s2. s3. alpha\nbeta "
    assert "\n" in result["before"]
    assert "s1." not in result["before"]


def test_chinese_terminators_are_boundaries():
    quote = "引用内容"
    source = "第一句话结束。第二句话结束。第三句话结束。第四句话结束。" + quote + "后续句子。再后续。多余句。"
    result = quote_context(_ev(source, quote))
    assert result["before"] == "第二句话结束。第三句话结束。第四句话结束。"
    assert "第一句话结束" not in result["before"]
    assert result["after"] == "后续句子。再后续。"
    assert result["truncated"] is True


def test_unicode_preserved_verbatim():
    quote = '"café ☕ ok"'
    source = "préfix ☃ data. " + quote + " suffix."
    result = quote_context(_ev(source, quote))
    assert result["before"] == "préfix ☃ data. "
    assert result["after"] == " suffix."
    assert result["truncated"] is False


def test_malformed_inputs_return_empty_dict():
    assert quote_context(None) == {}
    assert quote_context(["sourceContext"]) == {}
    assert quote_context({"sourceContext": "abc"}) == {}
    assert quote_context({"quote": "abc"}) == {}
    assert quote_context({"sourceContext": 5, "quote": "a"}) == {}
    assert quote_context({"sourceContext": None, "quote": "a"}) == {}
    assert quote_context({"sourceContext": "abc", "quote": ["a"]}) == {}
    assert quote_context({"sourceContext": "abc", "quote": True}) == {}
    assert quote_context({"sourceContext": "abc", "quote": ""}) == {}
    assert quote_context({"sourceContext": "abc", "quote": "xyz"}) == {}


def test_repeated_quote_uses_first_occurrence_deterministically():
    quote = "Q"
    source = "one. Q mid. two. three. Q late. four."
    first = quote_context(_ev(source, quote))
    second = quote_context(_ev(source, quote))
    assert first == second
    assert first["before"] == "one. "
    assert first["after"] == " mid. two."
    assert first["truncated"] is True


def test_no_mutation_of_evidence():
    evidence = {
        "sourceContext": "a. b. Q c. d. e.",
        "quote": "Q",
        "extra": {"nested": [1, 2]},
    }
    snapshot = copy.deepcopy(evidence)
    quote_context(evidence, window=300)
    assert evidence == snapshot


def test_window_validation_and_clamping():
    quote = "Q"
    source = "x" * 3000 + " Q"
    for bad in (True, False, "wide", None, [], float("nan"), float("inf")):
        assert len(quote_context(_ev(source, quote), window=bad)["before"]) == 1000
    assert len(quote_context(_ev(source, quote), window=-5)["before"]) == 1000
    assert len(quote_context(_ev(source, quote), window=1500.9)["before"]) == 1500
    assert len(quote_context(_ev(source, quote), window=5000)["before"]) == 2000
    assert len(quote_context(_ev(source, quote), window=2000)["before"]) == 2000
    assert len(quote_context(_ev(source, quote), window=0)["before"]) == 1000


def test_untruncated_result_reconstructs_source_exactly():
    source = "A. B says \"hi there\" politely. C."
    quote = '"hi there"'
    result = quote_context(_ev(source, quote))
    assert result["truncated"] is False
    assert result["before"] + quote + result["after"] == source


def test_header_metadata_without_boundaries_is_literal_preceding_text():
    quote = "the claim"
    source = "Paper 42, Journal of Tests, 2024\n\n" + quote + " holds."
    result = quote_context(_ev(source, quote))
    assert result["before"] == "Paper 42, Journal of Tests, 2024\n\n"
    assert result["after"] == " holds."
    assert result["truncated"] is False


def test_truncated_false_only_when_nothing_omitted():
    quote = "q"
    full = quote_context(_ev("a. q b.", quote))
    assert full["before"] == "a. "
    assert full["after"] == " b."
    assert full["truncated"] is False

    front = quote_context(_ev("w. x. y. z. q", quote))
    assert front["before"] == " x. y. z. "
    assert front["truncated"] is True

    back = quote_context(_ev("q a. b. c.", quote))
    assert back["after"] == " a. b."
    assert back["truncated"] is True


def test_exclamation_mark_ends_sentence_and_nothing_is_invented():
    quote = "stop"
    source = "Wait! Go now. " + quote + "?"
    result = quote_context(_ev(source, quote))
    assert result["before"] == "Wait! Go now. "
    assert result["after"] == "?"
    assert result["truncated"] is False

