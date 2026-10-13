import pytest
from services.deep_research.literal_quote import original_quote_span


def test_restores_original_whitespace_for_exact_source_context():
    original = 'Before. The decoder\n predicts\tthree offsets. After.'
    assert original_quote_span('The decoder predicts three offsets.', original) == 'The decoder\n predicts\tthree offsets.'


@pytest.mark.parametrize('quote', [
    'The decoder predicts four offsets.',
    'The encoder predicts three offsets.',
    'The decoder predicts three offsets!',
    'The decoder predicts 30 offsets.',
])
def test_never_repairs_changed_words_numbers_or_punctuation(quote):
    assert original_quote_span(quote, 'The decoder\npredicts three offsets.') is None


def test_ambiguous_whitespace_match_is_not_assigned_an_arbitrary_span():
    assert original_quote_span('same text', 'same\ntext; same\ttext') is None


def test_existing_exact_quotes_and_hyphenated_words_are_not_rewritten():
    assert original_quote_span('same text', 'same text and same text') == 'same text'
    assert original_quote_span('decoder', 'de-\ncoder') is None
    assert original_quote_span('', 'source') is None
