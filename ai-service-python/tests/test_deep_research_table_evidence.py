import json

from services.deep_research.local_sources import _indexed_source
from services.deep_research.table_evidence import attach_table_packet, visible_table_packet


def packet():
    return {'groups': [['Dataset A', ['FPS', 'Mem']], ['Dataset B', ['FPS', 'Mem']]],
            'rows': [[1, 'Baseline', ['30', '400MB', '40', '500MB']],
                     [2, 'Ours*', ['60', '100MB', '70', '120MB']]]}


def row_text(row):
    return f'Table row {row[0]}: ' + ' | '.join([row[1], *row[2]])


def test_packet_retains_dataset_and_variant_but_only_cited_complete_rows():
    data = packet()
    body = '\n'.join(row_text(row) for row in data['rows'])
    indexed = _indexed_source({'text': body, 'metadata': {'table_verified_data': json.dumps(data)}})
    assert indexed['tableData'] == data
    evidence = attach_table_packet({'quote': row_text(data['rows'][1]), 'sourceContext': body}, indexed)
    assert evidence['tableData'] == {'groups': data['groups'], 'rows': [data['rows'][1]]}
    assert evidence['tableData']['rows'][0][1] == 'Ours*'


def test_fragment_or_numeric_coincidence_does_not_create_table_support():
    data = packet()
    for quote in ['Ours* achieves 60 FPS', row_text(data['rows'][1])[:-1],
                  row_text(data['rows'][1]) + 'invalid', '60 100MB 70 120MB']:
        assert visible_table_packet(data, quote) is None
    assert 'tableData' not in attach_table_packet({'quote': '60 FPS'}, {'tableData': data})


def test_bad_column_mapping_or_unparsed_table_is_not_promoted():
    data = packet()
    body = '\n'.join(row_text(row) for row in data['rows'])
    data['groups'][0][1].append('PSNR')
    assert visible_table_packet(data, body) is None
    for raw in ['invalid json', {}, {'groups': [], 'rows': []}, None]:
        assert visible_table_packet(raw, body) is None
    assert _indexed_source({'text': body, 'metadata': {'table_column_mapping_unverified': True}})['tableData'] is None
