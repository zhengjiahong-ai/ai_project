import React, { useEffect, useRef, useState } from 'react';

export default function TaskRename({ task, onRename }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(task.title || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const trigger = useRef(null);
  const dialog = useRef(null);
  const wasOpen = useRef(false);
  useEffect(() => {
    if (!open && wasOpen.current) trigger.current?.focus();
    wasOpen.current = open;
  }, [open]);
  useEffect(() => { if (open && busy) dialog.current?.focus(); }, [open, busy]);
  const submit = async event => {
    event.preventDefault();
    if (busy || !title.trim()) return;
    setBusy(true); setError('');
    try { await onRename(title.trim()); setOpen(false); }
    catch (failure) { setError(failure.response?.data?.message || failure.message || '名称保存失败，请重试'); }
    finally { setBusy(false); }
  };
  return <>
    <button type="button" ref={trigger} className="unified-header-action" onClick={() => { setTitle(task.title || ''); setError(''); setOpen(true); }}>重命名</button>
    {open && <div className="task-draft-backdrop"><section ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-label="重命名任务" className="task-draft-dialog theme-panel"
      onKeyDown={event => {
        if (event.key === 'Escape' && !busy) { event.stopPropagation(); setOpen(false); }
        if (event.key !== 'Tab') return;
        const controls = [...event.currentTarget.querySelectorAll('input,button')].filter(element => !element.disabled);
        if (!controls.length) { event.preventDefault(); dialog.current?.focus(); return; }
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) { event.preventDefault(); first.focus(); }
      }}>
      <form onSubmit={submit}>
        <h2>任务名称</h2>
        <input autoFocus aria-label="任务名称" value={title} maxLength={500} disabled={busy} onChange={event => setTitle(event.target.value)} className="theme-input unified-rename-input" />
        {error && <p role="alert">{error}</p>}
        <div className="unified-document-toolbar">
          <button type="submit" disabled={busy || !title.trim()}>{busy ? '保存中…' : '保存名称'}</button>
          <button type="button" disabled={busy} onClick={() => setOpen(false)}>取消</button>
        </div>
      </form>
    </section></div>}
  </>;
}
