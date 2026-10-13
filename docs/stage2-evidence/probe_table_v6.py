"""Read a public test paper from the local service and inspect GROBID output."""
import hashlib
import json
import os
from pathlib import Path
import sys

import requests
from bs4 import BeautifulSoup

HERE = Path(os.environ.get('TABLE_PROBE_DIR') or Path(__file__).parent)
sys.path.insert(0, str(HERE.parents[1] / 'ai-service-python'))
from core.document_parser import parse_tei_xml

PAPER = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
TASK = 'task:f8b18af5-9681-4bda-ad15-30fd2f3dbafe'
tei = HERE / 'stage4-tables-v6-light.tei.xml'
if not tei.exists():
    paper = requests.get(f'http://127.0.0.1:8081/api/task-workspaces/{TASK}/materials/{PAPER}/file', timeout=30)
    paper.raise_for_status()
    assert hashlib.sha256(paper.content).hexdigest() + '.pdf' == PAPER
    response = requests.post('http://127.0.0.1:8070/api/processFulltextDocument',
                             files={'input': ('paper.pdf', paper.content, 'application/pdf')},
                             data={'teiCoordinates': ['figure', 'table', 'head', 'p']}, timeout=90)
    response.raise_for_status()
    tei.write_text(response.text, encoding='utf-8')
soup = BeautifulSoup(tei.read_text(encoding='utf-8'), 'xml')
sections = parse_tei_xml(str(tei))
body = soup.find('body')
table_figures = [figure for figure in soup.find_all('figure')
                 if figure.get('type') == 'table' or figure.find('table')]
report = {'paperId': PAPER, 'scope': 'Local GROBID parse and section extraction only',
          'providerCalls': 0, 'indexWrites': 0, 'tableCount': len(table_figures),
          'tables': [{'id': table.get('xml:id'), 'insideDiv': bool(table.find_parent('div')),
                      'insideBody': bool(table.find_parent('body')),
                      'head': table.find('head').get_text(' ', strip=True) if table.find('head') else '',
                      'label': table.find('label').get_text(' ', strip=True) if table.find('label') else '',
                      'text': table.get_text(' ', strip=True), 'coords': table.get('coords')}
                     for table in table_figures],
          'sectionCount': len(sections),
          'parsedTableSections': [section for section in sections if section.get('section', '').startswith('Table')],
          'parsedHasMainTableRow': any('27.40' in section['content'] and '782' in section['content'] for section in sections)}
(HERE / 'stage4-tables-v6-probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: report[k] for k in ('tableCount', 'sectionCount', 'parsedHasMainTableRow')}, ensure_ascii=False))
print(json.dumps([{k: row[k] for k in ('id','insideDiv','insideBody','head','label')} for row in report['tables']], ensure_ascii=False))
print('TABLE_PROBE_JSON=' + json.dumps(report, ensure_ascii=False))
