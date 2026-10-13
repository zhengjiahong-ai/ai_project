import React, { useState } from 'react';
import SourceList from './SourceCitation';
import { documentSources } from '../utils/documentSources';

export default function CollapsedSources({ value, onJumpToSource, storageKey = null }) {
  const [open, setOpen] = useState(() => {
    try { return Boolean(storageKey && localStorage.getItem(storageKey) === 'open'); }
    catch { return false; }
  });
  const sources = documentSources(value);
  if (!sources.length) return null;
  return <details className="reader-chat-citations" open={open} onToggle={event => {
    const next = event.currentTarget.open;
    setOpen(next);
    if (storageKey) {
      try { localStorage.setItem(storageKey, next ? 'open' : 'closed'); }
      catch { /* Optional reading preference. */ }
    }
  }}><summary>证据片段（{sources.length}）</summary>
    <SourceList sources={sources} onJumpToSource={onJumpToSource} />
  </details>;
}
