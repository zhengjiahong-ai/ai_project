"""Tables must survive parsing and bounded chunking without invented columns."""
import pytest

from core.document_parser import parse_tei_xml
from core.smart_chunker import chunk_sections, CHUNK_MAX_SIZE


def parse(tmp_path, body, extra=''):
    pytest.importorskip('lxml')
    path = tmp_path / 'paper.tei.xml'
    path.write_text(f'<TEI><teiHeader>{extra}</teiHeader><text><body>{body}</body>'
                    '<back><table><row><cell>excluded bibliography</cell></row></table></back>'
                    '</text></TEI>', encoding='utf-8')
    return parse_tei_xml(str(path))


def test_body_level_and_nested_tables_keep_cells_spans_pages_without_duplicate_caption(tmp_path):
    table = '''<figure type="table" xml:id="t1" coords="6,10,20,30,40">
      <head>Table 1</head><figDesc><p>Original benchmark caption</p></figDesc><table>
      <row><cell>Methods</cell><cell cols="2">Dataset A FPS Size</cell></row>
      <row><cell>Baseline *</cell><cell>144</cell><cell>782 MB</cell></row>
      <row><cell>Ours</cell><cell>237</cell><cell>45 MB</cell></row></table></figure>'''
    sections = parse(tmp_path, '<div><head>Results</head><p>Original prose</p>' +
                     table + '</div>' + table.replace('t1', 't2'))
    tables = [s for s in sections if s.get('evidenceKind') == 'table']
    assert len(tables) == 2
    assert {s['tableId'] for s in tables} == {'t1', 't2'}
    assert tables[0]['pageIndex'] == 5 and tables[0]['page'] == 6
    assert tables[0]['tableColumnMappingUnverified'] is True
    assert tables[0]['tableRows'][0][1] == {'text': 'Dataset A FPS Size', 'cols': 2, 'rows': 1}
    assert 'Baseline * | 144 | 782 MB' in tables[0]['content']
    assert 'Dataset A FPS Size [cols=2, rows=1]' in tables[0]['content']
    assert next(s for s in sections if s['section'] == 'Results')['content'] == 'Original prose'
    assert 'excluded bibliography' not in '\n'.join(s['content'] for s in sections)


def test_caption_only_table_and_bare_table_are_preserved(tmp_path):
    sections = parse(tmp_path, '<figure type="table" xml:id="caption"><head>Table 2</head>'
                     '<figDesc>Values could not be parsed</figDesc></figure>'
                     '<table xml:id="bare"><row><cell>Baseline</cell><cell>10 FPS</cell></row></table>',
                     '<table><row><cell>excluded header</cell></row></table>')
    assert len(sections) == 2
    assert sections[0]['tableColumnMappingUnverified'] is True
    assert 'Values could not be parsed' in sections[0]['content']
    assert sections[1]['tableRows'][0][0]['text'] == 'Baseline'
    assert 'excluded header' not in '\n'.join(s['content'] for s in sections)


def test_table_chunks_repeat_original_first_row_and_do_not_mix_rows_from_other_tables():
    prefix = 'Table caption: Table 1\nTable row 1: Method | FPS | Size'
    rows = [f'Table row {i + 2}: method-{i} | {i} | ' + 'original value ' * 10 for i in range(12)]
    chunks = chunk_sections([{'id': 'table-t1', 'section': 'Table 1', 'evidenceKind': 'table',
                             'tableId': 't1', 'tablePrefix': prefix, 'pageIndex': 5,
                             'content': '\n'.join([prefix, *rows])},
                            {'section': 'Table 2', 'evidenceKind': 'table', 'tableId': 't2',
                             'content': 'second table only'}])
    first = [c for c in chunks if c['tableId'] == 't1']
    assert len(first) > 1
    assert all(c['text'].startswith(prefix) and c['pageIndex'] == 5 for c in first)
    assert all(len(c['text']) <= CHUNK_MAX_SIZE for c in chunks)
    assert [line for c in first for line in c['text'].splitlines()[2:]] == rows
    assert chunks[-1]['text'].strip() == 'second table only'


@pytest.mark.parametrize('long_header', [False, True])
def test_oversized_table_text_is_retained_bounded_and_marked_unverified(long_header):
    prefix = 'Table caption: T\nTable row 1: ' + ('h' * 3000 if long_header else 'Method | Value')
    row = 'Table row 2: ' + 'v' * 4100
    chunks = chunk_sections([{'section': 'Table 1', 'evidenceKind': 'table', 'tableId': 't1',
                             'tablePrefix': prefix, 'tableColumnMappingUnverified': False,
                             'content': prefix + '\n' + row}])
    assert all(len(c['text']) <= CHUNK_MAX_SIZE for c in chunks)
    assert all(c['tableColumnMappingUnverified'] is True for c in chunks)
    if long_header:
        combined = ''.join(c['text'] for c in chunks)
        assert combined.count('h') == prefix.count('h') and combined.count('v') == row.count('v')
    else:
        assert ''.join(c['text'][len(prefix) + 1:] for c in chunks) == row
