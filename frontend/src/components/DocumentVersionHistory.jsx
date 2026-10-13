import React, { useState } from 'react';
import MarkdownContent from './MarkdownContent';
import { documentText } from '../utils/documentVersions';

export default function DocumentVersionHistory({ document, onRestore, disabled = false, expanded = false }) {
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const versions = document.versions || [];
  const version = selected === null ? null : versions[selected];
  const restore = async () => {
    if (disabled || busy) return;
    setBusy(true); setError('');
    try { await onRestore(version); setSelected(null); }
    catch (failure) { setError(failure.message || '恢复失败，当前内容仍保留'); }
    finally { setBusy(false); }
  };
  if (!versions.length) return null;
  return <details className="document-version-history" open={expanded || undefined}><summary>历史版本（{versions.length}）</summary>
    {!versions.length && <p>保存修改后，先前正文会保存在这里。</p>}
    {versions.length > 0 && <select aria-label="选择历史版本" value={selected ?? ''} disabled={busy} onChange={(event) => { setSelected(event.target.value === '' ? null : Number(event.target.value)); setError(''); }}>
      <option value="">选择要查看的版本</option>
      {versions.map((item, index) => <option key={index} value={index}>{index + 1} · {item.savedAt ? new Date(item.savedAt).toLocaleString() : '旧版本'}{item.kind === 'unsaved-draft' ? ' · 编辑草稿' : ''}</option>).reverse()}
    </select>}
    {version && <div><MarkdownContent>{documentText(version) || '（空白正文）'}</MarkdownContent>
      <p>恢复会保留当前正文及未保存的编辑。</p>
      <button type="button" disabled={busy || disabled} onClick={restore}>{busy ? '恢复中…' : '恢复这个版本'}</button>
    </div>}
    {error && <p role="alert">{error}</p>}
  </details>;
}
