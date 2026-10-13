from services.deep_research.external import _page_passages


def test_sentence_crossing_old_cut_remains_intact_with_exact_offsets():
    sentence = 'This method connects nearby Gaussians and decodes their deformation.'
    text = 'a' * 1970 + '.\n' + sentence + '\n' + 'following paragraph. ' * 90
    chunks = list(_page_passages(text))
    assert ''.join(chunk for _, chunk in chunks) == text
    assert any(sentence in chunk for _, chunk in chunks)
    assert all(text[offset:offset + len(chunk)] == chunk for offset, chunk in chunks)
    assert all(0 < len(chunk) <= 3000 for _, chunk in chunks)


def test_long_unpunctuated_input_stays_bounded_and_makes_progress():
    text = 'x' * 9000
    chunks = list(_page_passages(text))
    assert [offset for offset, _ in chunks] == [0, 2000, 4000]
    assert ''.join(chunk for _, chunk in chunks) == text[:6000]


def test_long_sentence_prefers_whitespace_without_rewriting():
    text = 'word-with-hyphens ' * 400
    chunks = list(_page_passages(text))
    assert ''.join(chunk for _, chunk in chunks) == text[:6000]
    assert all(chunk.endswith(' ') for _, chunk in chunks[:-1])
    assert list(_page_passages('')) == []
