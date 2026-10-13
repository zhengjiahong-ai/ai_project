"""Carry parser-established table cells without promoting model guesses."""
import json


def visible_table_packet(raw, text):
    if isinstance(raw, str):
        if len(raw) > 40000:
            return None
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(raw, dict):
        return None
    groups, rows = raw.get('groups'), raw.get('rows')
    if not isinstance(groups, list) or not groups or not isinstance(rows, list):
        return None
    if any(not isinstance(g, list) or len(g) != 2 or not isinstance(g[0], str)
           or not isinstance(g[1], list) or not g[1]
           or any(not isinstance(m, str) for m in g[1]) for g in groups):
        return None
    columns = sum(len(g[1]) for g in groups)
    visible = []
    for row in rows:
        if (not isinstance(row, list) or len(row) != 3 or not isinstance(row[0], int)
                or not isinstance(row[1], str) or not isinstance(row[2], list)
                or len(row[2]) != columns or any(not isinstance(v, str) for v in row[2])):
            return None
        literal = f'Table row {row[0]}: ' + ' | '.join([row[1], *row[2]])
        if literal in {line.strip() for line in text.splitlines()}:
            visible.append(row)
    return {'groups': groups, 'rows': visible} if visible else None


def attach_table_packet(evidence, source):
    # A readable surrounding paragraph is not a citation for another row.
    packet = visible_table_packet(source.get('tableData'), evidence['quote'])
    if packet:
        evidence['tableData'] = packet
    return evidence
