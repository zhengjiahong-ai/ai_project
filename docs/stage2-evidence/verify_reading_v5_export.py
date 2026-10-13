"""Read-only audit of the actual browser download; never calls a model."""
import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
saved = json.loads((HERE / 'stage6-reading-v5-saved-runtime.json').read_text(encoding='utf-8'))
browser = json.loads((HERE / 'stage6-reading-v5-export-browser.json').read_text(encoding='utf-8'))
html_bytes = (HERE / 'stage6-reading-v5-actual-export.html').read_bytes()
html = html_bytes.decode('utf-8')
with urlopen('http://127.0.0.1:8081/api/task-workspaces/task%3Af8b18af5-9681-4bda-ad15-30fd2f3dbafe', timeout=30) as response:
    task = json.load(response)
artifact = saved['newArtifact']
live_artifact = next(item for item in task['artifacts'] if item['id'] == artifact['id'])
normalize = lambda text: re.sub(r'\s+', '', text)
# This saved page contains only prose, a heading and a blockquote notice; no
# mathematical Markdown is rewritten to claim arbitrary rendering equivalence.
plain_source = re.sub(r'^\s*(?:>\s*|#{1,6}\s+)', '', artifact['text'], flags=re.M)
images = re.findall(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', html)
checks = {
    'savedArtifactUnchanged': live_artifact == artifact,
    'historicalDocumentsAndMessagesUnchanged': all(task[key] == saved['task'][key] for key in ('notes', 'artifacts', 'messages')),
    'taskRevisionUnchanged': task['revision'] == saved['task']['revision'],
    'visibleArticleMatchesSavedText': normalize(browser['articleText']) == normalize(plain_source),
    'savedPaperAndPageMatch': artifact['paperIds'][0] in browser['sourceText'] and '第 4 页' in browser['sourceText'],
    'embeddedOriginalLoaded': len(images) == 1 and all(image['loaded'] and image['embedded'] for image in browser['images']),
    'standaloneWithoutScriptsOrStylesheets': browser['scriptCount'] == browser['stylesheetLinks'] == 0,
    'oldContentErrorPreserved': '用 1 减去 Q' in browser['articleText'],
}
result = {
    'scope': 'Actual v5 browser download and static-file display; not corrected translation quality acceptance',
    'checks': checks, 'htmlBytes': len(html_bytes), 'htmlSha256': hashlib.sha256(html_bytes).hexdigest(),
    'pngBytes': len(base64.b64decode(images[0])), 'sourcePage': 4, 'artifactId': artifact['id'],
    'taskRevision': task['revision'], 'providerCalls': 0, 'taskWrites': 0,
    'downloadEventObserved': False, 'downloadFileObserved': True,
    'previewDirectoryScope': 'tmp/stage6-html-review-20261009a contains only this HTML',
}
(HERE / 'stage6-reading-v5-export-runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
assert all(checks.values())
