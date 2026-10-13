"""Inspect actual embedded-font encoding around the damaged product; read-only."""
import json
from pathlib import Path
from PyPDF2 import PdfReader

path = Path('D:/3DGS/paper/LightGaussian/2311.17245v6.pdf')
reader = PdfReader(path)
page = reader.pages[3]
rows = []
for key, ref in page['/Resources']['/Font'].items():
    font = ref.get_object()
    encoding = font.get('/Encoding')
    if encoding is not None:
        encoding = encoding.get_object()
    cmap = font.get('/ToUnicode')
    text = cmap.get_object().get_data().decode('latin1') if cmap else ''
    descriptor = font.get('/FontDescriptor')
    file = descriptor.get_object().get('/FontFile') if descriptor else None
    operator_encoding = []
    if file:
        file = file.get_object()
        length = int(file.get('/Length1', 0))
        if 0 < length <= 262144:
            header = file.get_data()[:length].decode('latin1')
            operator_encoding = [line.strip() for line in header.splitlines()
                                 if '/product' in line or '/summation' in line]
    rows.append({'resource': str(key), 'fontName': str(font.get('/BaseFont')),
                 'subtype': str(font.get('/Subtype')), 'encoding': str(encoding),
                 'originalOperatorEncoding': operator_encoding,
                 'unicodeMap': text if 'cmex' in str(font.get('/BaseFont')).lower() else None})
result = {'scope': 'Physical page 4 embedded-font dictionaries, no font-name guessing',
          'source': str(path), 'fonts': rows}
Path('docs/stage2-evidence/stage6-math-font-v9.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
