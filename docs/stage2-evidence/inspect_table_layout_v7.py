"""Read-only PDF layout diagnostic using the bundled document runtime."""
import hashlib
import json
import sys
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

sys.stdout.reconfigure(encoding='utf-8')

SOURCE = Path('D:/3DGS/paper/LightGaussian/2311.17245v6.pdf')
HERE = Path(__file__).parent
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634'
with pdfplumber.open(SOURCE) as pdf:
    page = pdf.pages[5]
    words = page.extract_words()
    lines = []
    for word in sorted(words, key=lambda word: (round(word['top'] / 3), word['x0'])):
        if word['top'] > 200:
            continue
        if not lines or abs(lines[-1]['top'] - word['top']) > 3:
            lines.append({'top': word['top'], 'words': []})
        lines[-1]['words'].append({'text': word['text'], 'x0': word['x0'], 'x1': word['x1']})
    text = page.extract_text()
reader = PdfReader(SOURCE)
runs = []
def visitor(text, cm, tm, font, size):
    if text.strip():
        runs.append({'text': text, 'cm': cm, 'tm': tm, 'fontSize': size})
reader.pages[5].extract_text(visitor_text=visitor)
report = {'source': str(SOURCE), 'pageIndex': 5, 'pageSize': [page.width, page.height],
          'words': lines, 'text': text, 'visitorRuns': runs, 'providerCalls': 0}
(HERE / 'stage4-table-layout-v7.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
for line in lines:
    print(round(line['top'], 1), ' | '.join(f"{word['text']}@{word['x0']:.1f}" for word in line['words']))
print('PDF visitor runs:', len(runs))
