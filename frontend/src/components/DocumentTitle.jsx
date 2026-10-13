import React, { useState } from 'react';

export default function DocumentTitle({ title, onRename }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!onRename) return <span className="unified-document-title">{title || '成果'}</span>;
  if (!editing) return <button type="button" className="unified-document-title" title={title} aria-label="修改成果名称" onClick={() => { setDraft(title || ''); setEditing(true); }}>{title || '笔记'}</button>;
  return <form className="unified-document-title-edit" onSubmit={async event => {
    event.preventDefault(); if (busy || !draft.trim()) return;
    setBusy(true); setError('');
    try { await onRename(draft.trim()); setEditing(false); } catch (failure) { setError(failure.message || '名称保存失败'); }
    finally { setBusy(false); }
  }}>
    <input autoFocus aria-label="修改成果名称" value={draft} maxLength={500} disabled={busy} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Escape' && !busy) setEditing(false); }} />
    <button type="submit" disabled={busy || !draft.trim()}>{busy ? '保存中' : '保存名称'}</button><button type="button" disabled={busy} onClick={() => setEditing(false)}>取消</button>
    {error && <span role="alert">{error}</span>}
  </form>;
}
