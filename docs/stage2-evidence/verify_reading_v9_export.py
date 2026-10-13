"""Audit the actual v9-artifact browser download. No Provider or task writes."""
import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
saved = json.loads((HERE / 'stage6-reading-v9-after-save.json').read_text(encoding='utf-8'))
browser = json.loads((HERE / 'stage6-reading-v9-export-browser.json').read_text(encoding='utf-8'))
html_bytes = (HERE / 'stage6-reading-v9-actual-export.html').read_bytes()
html = html_bytes.decode('utf-8')
with urlopen('http://127.0.0.1:8081/api/task-workspaces/task%3Af8b18af5-9681-4bda-ad15-30fd2f3dbafe', timeout=30) as response:
    task = json.load(response)
artifact = next(item for item in saved['artifacts'] if item['id'] == '882613db-8f6e-4c27-9f3a-bc2bdfc85cff')
live_artifact = next(item for item in task['artifacts'] if item['id'] == artifact['id'])
normalize = lambda text: re.sub(r'\s+', '', text)
# Only this known prose/blockquote fixture is compared; no general math equivalence claim.
plain_source = re.sub(r'^\s*(?:>\s*|#{1,6}\s+)', '', artifact['text'], flags=re.M)
images = re.findall(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', html)
checks = {
    'savedArtifactUnchanged': live_artifact == artifact,
    'allTaskFieldsUnchanged': task == saved,
    'visibleArticleMatchesSavedText': normalize(browser['articleText']) == normalize(plain_source),
    'savedPaperAndPageMatch': artifact['paperIds'][0] in browser['sourceText'] and '第 4 页' in browser['sourceText'],
    'embeddedOriginalLoaded': len(images) == 1 and len(browser['images']) == 1 and all(image['loaded'] and image['embedded'] for image in browser['images']),
    'standaloneWithoutScriptsOrStylesheets': browser['scriptCount'] == browser['stylesheetLinks'] == 0,
    'sourcesInitiallyCollapsed': browser['sourceCollapsed'],
    'unsafeSubtractAllAbsent': '减去' not in browser['articleText'] and '一减项' in browser['articleText'],
    'eightUniqueMarkers': set(re.findall(r'⟦原式[1-8]⟧', browser['articleText'])) == {f'⟦原式{i}⟧' for i in range(1,9)},
    'oldArtifactsUnchanged': all(next(a for a in task['artifacts'] if a['id']==old['id'])==old for old in json.loads((HERE/'stage6-reading-v9-before.json').read_text(encoding='utf-8'))['artifacts']),
}
result = {
    'scope': 'Actual v9 artifact download and independent static-file display; new conservative transmittance translation and eight markers verified; does not prove all-paper translation quality',
    'checks': checks, 'htmlBytes': len(html_bytes), 'htmlSha256': hashlib.sha256(html_bytes).hexdigest(),
    'pngBytes': len(base64.b64decode(images[0])), 'sourcePage': 4, 'artifactId': artifact['id'],
    'taskRevision': task['revision'], 'providerCalls': 0, 'taskWrites': 0,
    'downloadEventObserved': False, 'downloadFileObserved': True,
    'previewDirectoryScope': 'tmp/stage6-html-review-v9 contains only this HTML',
}
(HERE / 'stage6-reading-v9-export-runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
assert all(checks.values())
