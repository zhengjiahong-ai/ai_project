"""Two fixed public-paper cases; preserve raw provider output, never auto-retry.

Run once from the project root. Existing files prevent duplicate submissions.
This exercises the actual synthesis/check/presentation path, not retrieval/indexing.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ai-service-python'))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
os.chdir(ROOT)

from PyPDF2 import PdfReader
from services.focused_evidence import select_critique_evidence
from services.grounded_critique import synthesize_critique
from services.socratic_service import _call_guarded_llm

PAPER = Path(r'D:\3DGS\paper\LightGaussian\2311.17245v6.pdf')
OUT = ROOT / 'docs' / 'critique-evidence-20261011'
OUT.mkdir(exist_ok=True)
pages = PdfReader(PAPER).pages
corpus = []
for page_index in range(2, min(9, len(pages))):
    body = pages[page_index].extract_text() or ''
    # Preserve each continuous extracted window with its page and original text.
    for offset in range(0, len(body), 1500):
        text = body[offset:offset + 1800]
        section = 'Method' if page_index < 5 else 'Experimental Results' if page_index < 7 else 'Limitations and Experiments'
        corpus.append({'sourceId': f'light-p{page_index + 1}-{offset}', 'pdfId': 'LightGaussian-public',
                       'pageIndex': page_index, 'chunkIndex': len(corpus), 'text': text,
                       'metadata': {'section_title': section}})
cases = [
    ('focused', '只依据LightGaussian：压缩后“画质几乎不变”的主张在什么条件下成立？给最关键的两点，用150字回答，不做全面综述。不要给数字排名，优先核对直接实验结果及条件。'),
    ('review', '对LightGaussian作批判阅读：最影响复现和使用决策的两个判断是什么？区分作者报告、设计推断和待核查问题。不要强行给每个机制配一个缺点，不写数值排名。'),
]
if '--context-fix' in sys.argv:
    cases = [(name + '-context', question) for name, question in cases]
if '--quality-fix' in sys.argv:
    cases = [(name + '-quality', question) for name, question in cases]
for name, question in cases:
    result_path = OUT / f'{name}.json'
    attempt_path = OUT / f'{name}-attempt.json'
    if attempt_path.exists():
        print(name + ': existing attempt retained; no submission')
        continue
    sources = select_critique_evidence(corpus, corpus, question, limit=10)
    attempt_path.write_text(json.dumps({'question': question, 'paper': str(PAPER), 'sourceIds': [s['sourceId'] for s in sources],
                                      'calls': 0, 'sources': sources}, ensure_ascii=False, indent=2), encoding='utf-8')
    captured = {'question': question, 'sources': sources, 'providerCalls': 0}
    def model(prompt, extra_system_instruction=''):
        captured['providerCalls'] += 1
        captured['prompt'] = prompt
        # Write before sending so interruption cannot silently duplicate a call.
        attempt_path.write_text(json.dumps({'question': question, 'paper': str(PAPER), 'calls': captured['providerCalls'],
                                          'sourceIds': [s['sourceId'] for s in sources]}, ensure_ascii=False, indent=2), encoding='utf-8')
        raw = _call_guarded_llm(prompt, extra_system_instruction)
        captured['rawResponse'] = raw
        result_path.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding='utf-8')
        return raw
    try:
        with patch('services.socratic_service._call_guarded_llm', side_effect=model):
            captured['result'] = synthesize_critique(question, sources, allow_partial=True)
    except Exception as error:
        captured['error'] = str(error)
    result_path.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'case': name, 'calls': captured['providerCalls'], 'error': captured.get('error'),
                      'summary': captured.get('result', {}).get('summary'),
                      'issues': len(captured.get('result', {}).get('critique', {}).get('issues', []))}, ensure_ascii=False))
