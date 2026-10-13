"""Cross-check simple grouped table columns against PDF drawing operations.

This deliberately leaves irregular/rotated/multiline tables unverified. The
private PyPDF2 font adapter is isolated here; unsupported adapters fail closed.
"""
import re
import unicodedata


def compact(text):
    return re.sub(r'\s+', '', str(text)).replace('∗', '*')


def drawing_runs(page):
    from PyPDF2._cmap import build_char_map

    fonts = {name: build_char_map(name, 200, page)[2:5]
             for name in page['/Resources']['/Font']}
    current_font = [None]
    font_size, horizontal_scale, char_space, word_space = [0], [1], [0], [0]
    runs = []

    def decode(value):
        encoding, cmap, _ = fonts[current_font[0]]
        raw = value if isinstance(value, bytes) else value.original_bytes
        if isinstance(encoding, str):
            decoded = raw.decode(encoding)
        else:
            decoded = ''.join(encoding.get(code, chr(code)) for code in raw)
        return ''.join(cmap.get(char, char) for char in decoded)

    def before(operator, operands, cm, tm):
        if operator == b'Tf':
            current_font[0] = operands[0]
            font_size[0] = float(operands[1])
        elif operator == b'Tz':
            horizontal_scale[0] = float(operands[0]) / 100
        elif operator == b'Tc':
            char_space[0] = float(operands[0])
        elif operator == b'Tw':
            word_space[0] = float(operands[0])
        if operator not in (b'Tj', b'TJ') or current_font[0] not in fonts:
            return
        # Rotated/skewed writing and unknown encodings do not verify a grid.
        if cm[1] or cm[2] or tm[1] or tm[2]:
            return
        values = operands[0] if operator == b'TJ' else operands
        try:
            text = ''.join(decode(value) for value in values if isinstance(value, (str, bytes)))
        except (LookupError, UnicodeError, AttributeError):
            return
        if text.strip():
            x = tm[4] * cm[0] + cm[4]
            y = float(page.mediabox.height) - (tm[5] * cm[3] + cm[5])
            tokens = []
            ft = fonts[current_font[0]][2]
            scale = tm[0] * cm[0] * horizontal_scale[0]
            cursor, token, token_x = x, '', x
            # Only simple byte fonts with explicit widths verify cell values.
            # Header labels can still be read, but unsupported values stay raw.
            supported = '/Widths' in ft and '/FirstChar' in ft
            for value in values if supported else []:
                if isinstance(value, (int, float)):
                    gap = -float(value) / 1000 * font_size[0] * scale
                    if gap > font_size[0] * scale * .18 and token:
                        tokens.append({'text': token, 'x': token_x})
                        token = ''
                    cursor += gap
                    continue
                raw = value if isinstance(value, bytes) else value.original_bytes
                for code in raw:
                    try:
                        letter = decode(bytes([code]))
                        width = float(ft['/Widths'][code - int(ft['/FirstChar'])])
                        if not 0 <= code - int(ft['/FirstChar']) < len(ft['/Widths']):
                            raise IndexError()
                    except (LookupError, UnicodeError, IndexError):
                        supported = False
                        break
                    if letter.isspace():
                        if token:
                            tokens.append({'text': token, 'x': token_x})
                            token = ''
                    else:
                        if not token:
                            token_x = cursor
                        token += letter
                    cursor += (width / 1000 * font_size[0] + char_space[0]
                               + (word_space[0] if code == 32 else 0)) * scale
                if not supported:
                    break
            if token:
                tokens.append({'text': token, 'x': token_x})
            runs.append({'text': text, 'x': x, 'y': y, 'tokens': tokens if supported else None})

    page.extract_text(visitor_operand_before=before)
    return runs


def verify_table_columns(section, runs):
    """Return only headers AND complete rows corroborated by PDF geometry."""
    bounds = section.get('tableBounds')
    rows = section.get('tableRows') or []
    if not bounds or len(rows) < 2:
        return None
    x, y, width, height = bounds
    inside = [run for run in runs if x - 2 <= run['x'] <= x + width + 2
              and y - 2 <= run['y'] <= y + height + 2]
    metrics = []
    for run in inside:
        # A single PDF text operation may draw several separated headings.
        for token in run.get('tokens') or [run]:
            name = unicodedata.normalize('NFKC', token['text'])
            if re.fullmatch(r'FPS|Size|Mem|Train|PSNR|SSIM|LPIPS', name, re.I):
                metrics.append({**token, 'text': name, 'y': run['y']})
    if len(metrics) < 4 or max(run['y'] for run in metrics) - min(run['y'] for run in metrics) > 1:
        return None
    metrics.sort(key=lambda run: run['x'])
    # Repeating an identical metric sequence anchors groups, rather than
    # expanding TEI colspan values whose labels may be damaged.
    names = [run['text'] for run in metrics]
    repeat = next((i for i in range(1, len(names)) if names[i].lower() == names[0].lower()), None)
    if not repeat or len(names) % repeat or any(names[i:i + repeat] != names[:repeat]
                                               for i in range(0, len(names), repeat)):
        return None
    header_y = metrics[0]['y']
    group_runs = sorted([run for run in inside if metrics[0]['x'] <= run['x'] <= metrics[-1]['x']
                         and re.search(r'[A-Za-z0-9]', run['text'])
                         and 1 < header_y - run['y'] < 20], key=lambda run: run['x'])
    if len(group_runs) != len(names) // repeat:
        return None
    group_labels = [cell['text'] for cell in rows[0] if cell['text'].strip()]
    # TEI may combine labels and metrics. Match the actual PDF group name
    # inside the header text, never infer it from a dataset list elsewhere.
    groups = []
    for i, run in enumerate(group_runs):
        column_runs = metrics[i * repeat:(i + 1) * repeat]
        if not column_runs[0]['x'] <= run['x'] <= column_runs[-1]['x']:
            return None
        label = next((label for label in group_labels if compact(run['text']).lower() in compact(label).lower()), None)
        if label is None:
            return None
        span = re.search(r'\s*'.join(re.escape(c) for c in compact(run['text'])), label, re.I)
        if span is None:
            return None
        groups.append([span.group().strip(), names[:repeat]])
    pdf_rows = []
    for run in sorted(inside, key=lambda run: (run['y'], run['x'])):
        if not pdf_rows or abs(pdf_rows[-1]['y'] - run['y']) > 3:
            pdf_rows.append({'y': run['y'], 'runs': []})
        pdf_rows[-1]['runs'].append(run)
    column_x = [run['x'] for run in metrics]
    first_boundary = column_x[0] - (column_x[1] - column_x[0]) / 2
    literal_rows = []
    for row in pdf_rows:
        if row['y'] <= header_y + 3 or any(run.get('tokens') is None for run in row['runs']):
            continue
        cells = [[] for _ in range(len(names) + 1)]
        for token in sorted([token for run in row['runs'] for token in run['tokens']], key=lambda token: token['x']):
            column = 0 if token['x'] < first_boundary else 1 + min(range(len(column_x)), key=lambda i: abs(column_x[i] - token['x']))
            cells[column].append(token['text'])
        literal_rows.append([compact(''.join(cell)) for cell in cells])
    checked = []
    for number, row in enumerate(rows[1:], 2):
        if not row or any(cell['rows'] != 1 for cell in row):
            continue
        values = [cell['text'] for cell in row]
        if len(row) != len(names) + 1:
            # Recover only explicit whitespace-separated cells, then require
            # every recovered cell to match an independently drawn PDF column.
            values = [values[0], *(part for value in values[1:] for part in value.split())]
            if len(values) != len(names) + 1:
                continue
        elif any(cell['cols'] != 1 for cell in row):
            continue
        if [compact(value) for value in values] not in literal_rows:
            continue
        checked.append([number, values[0], values[1:]])
    return {'groups': groups, 'rows': checked} if checked else None


def attach_verified_table_columns(sections, pdf_path):
    from PyPDF2 import PdfReader
    try:
        reader = PdfReader(pdf_path)
    except Exception:
        return sections
    pages = {}
    for section in sections:
        index = section.get('pageIndex')
        if section.get('evidenceKind') != 'table' or index is None or not 0 <= index < len(reader.pages):
            continue
        if reader.pages[index].get('/Rotate', 0) % 360:
            continue
        try:
            if index not in pages:
                pages[index] = drawing_runs(reader.pages[index])
            verified = verify_table_columns(section, pages[index])
        except (KeyError, ValueError, TypeError, ImportError, AttributeError):
            verified = None
        if verified:
            section['tableVerifiedData'] = verified
            # Keep normalized table text and the checked packet identical for
            # downstream exact-quote checks; untouched rows retain raw TEI text.
            lines = section.get('content', '').splitlines()
            replacements = {f'Table row {n}: ': ' | '.join([method, *values])
                            for n, method, values in verified['rows']}
            section['content'] = '\n'.join(next((prefix + value for prefix, value in replacements.items()
                                                if line.startswith(prefix)), line) for line in lines)
    return sections
