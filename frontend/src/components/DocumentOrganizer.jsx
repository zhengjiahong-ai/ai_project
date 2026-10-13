import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import DocumentVersionHistory from './DocumentVersionHistory';

export default function DocumentOrganizer({ document: record, displayTitle, kind = '成果', action, taskId, tasks = [], dirty, disabled,
  onRename, onMove, onRestore, onClose, getPendingMove = () => null }) {
  const [title, setTitle] = useState(displayTitle || record.title || '');
  const [pending, setPending] = useState(getPendingMove);
  const [target, setTarget] = useState(pending?.targetTaskId || '');
  const [includeMaterials, setIncludeMaterials] = useState(Boolean(pending?.includeMaterials));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const panel = useRef(null), headingId = useId();
  const label = action === 'rename' ? `重命名${kind}` : action === 'history' ? '历史版本' : `移动${kind}`;
  useEffect(() => {
    const previous = window.document.activeElement;
    panel.current?.querySelector('input, select, button:not(:disabled)')?.focus();
    return () => { if (previous?.isConnected) previous.focus(); };
  }, []);
  const perform = async operation => {
    setBusy(true); setError('');
    try { await operation(); onClose(); }
    catch (failure) { setError(failure.response?.data?.message || failure.message || '操作未完成，请稍后再试'); setPending(getPendingMove()); }
    finally { setBusy(false); }
  };
  return createPortal(<div className="task-draft-backdrop" onClick={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section ref={panel} role="dialog" aria-modal="true" aria-labelledby={headingId} className="task-draft-dialog theme-panel document-action-dialog" onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (!busy) onClose(); }
      if (event.key === 'Tab') {
        const elements = Array.from(panel.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), summary, [tabindex="0"]'));
        const first = elements[0], last = elements.at(-1);
        if (event.shiftKey && window.document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && window.document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }}>
      <h2 id={headingId}>{label}</h2>
      {action === 'rename' && <form onSubmit={event => { event.preventDefault(); if (!busy && title.trim()) perform(() => onRename(title.trim())); }}>
        <label>{kind}名称<input aria-label={`${kind}名称`} value={title} disabled={busy} maxLength={500} onChange={event => setTitle(event.target.value)} /></label>
        {error && <p role="alert">{error}</p>}
        <div className="document-action-footer"><button type="button" disabled={busy} onClick={onClose}>取消</button><button type="submit" className="workbench-primary" disabled={busy || !title.trim()}>{busy ? '保存中…' : '保存名称'}</button></div>
      </form>}
      {action === 'move' && <>
        <p className="document-action-name">{displayTitle || record.title || `未命名${kind}`}</p>
        {pending ? <><p role="status">移动结果待确认。请先检查是否已移动，再进行其他移动。</p><p>目标任务：{tasks.find(task => task.id === pending.targetTaskId)?.title || '之前选择的任务'}</p></> : <>
          <label>目标任务<select aria-label="移动到任务" value={target} disabled={busy} onChange={event => setTarget(event.target.value)}>
            <option value="">选择任务</option>{tasks.filter(task => task.id !== taskId && !task.archived).map(task => <option key={task.id} value={task.id}>{task.title}</option>)}
          </select></label>
          {!tasks.some(task => task.id !== taskId && !task.archived) && <p>暂无其他任务，请先创建一个目标任务。</p>}
          {target && record.paperIds?.length > 0 && <label className="document-action-checkbox"><input type="checkbox" checked={includeMaterials} disabled={busy} onChange={event => setIncludeMaterials(event.target.checked)} />同时添加关联论文</label>}
          <p>移动后，这份{kind}将从当前任务移到目标任务。</p>
          {dirty && <p role="status">请先保存正文，再移动{kind}。</p>}
        </>}
        {error && <p role="alert">{error}</p>}
        <div className="document-action-footer"><button type="button" disabled={busy} onClick={onClose}>取消</button>
          {pending ? <button type="button" disabled={busy || disabled} onClick={() => perform(() => onMove(null, false, true))}>{busy ? '检查中…' : '检查是否已移动'}</button>
            : <button type="button" className="workbench-primary" disabled={busy || disabled || dirty || !target || !(record.id || record.artifactId)} onClick={() => perform(() => onMove(target, includeMaterials, false))}>{busy ? '移动中…' : `移动${kind}`}</button>}
        </div>
      </>}
      {action === 'history' && <><DocumentVersionHistory document={record} onRestore={onRestore} disabled={disabled} expanded /><div className="document-action-footer"><button type="button" onClick={onClose}>关闭</button></div></>}
    </section>
  </div>, window.document.querySelector('.unified-app') || window.document.body);
}
