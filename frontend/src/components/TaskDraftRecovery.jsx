import React, { useEffect, useState } from 'react';
import { taskWorkspaceRemoteStore } from '../services/taskWorkspaceRemoteStore';

export function recoveryTask(snapshot, id) {
  const activityId = snapshot.activeActivity ? `${id}:learning` : undefined;
  return {
    ...snapshot, id, revision: undefined, title: `${snapshot.title || '任务'} · 恢复副本`,
    messages: (snapshot.messages || []).map((message) => ({ ...message,
      ...(message.context ? { context: { ...message.context, taskId: id,
        ...(activityId && message.context.activityId === (snapshot.activeActivity.activityId || snapshot.activeActivity.id) ? { activityId } : {}),
      } } : {}),
    })),
    activeActivity: snapshot.activeActivity ? { ...snapshot.activeActivity, id: activityId, activityId, taskId: id, status: 'paused' } : null,
  };
}

export default function TaskDraftRecovery({ taskId, refreshKey, onCreateTask, store = taskWorkspaceRemoteStore }) {
  const [draft, setDraft] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    setDraft(null); setOpen(false); setError('');
    const load = store.listUnsyncedDrafts ? store.listUnsyncedDrafts() : taskId ? store.getUnsyncedDraft(taskId).then(value => value ? [value] : []) : Promise.resolve([]);
    load.then((values) => {
      const value = values.find(item => item.task?.id === taskId) || values[0] || null;
      if (alive) { setDrafts(values); setDraft(value); setSelected(Math.max(0, (value?.versions?.length || 1) - 1)); }
    }).catch((failure) => { if (alive) setError(failure.message || '草稿读取失败'); });
    return () => { alive = false; };
  }, [taskId, refreshKey, store]);
  const versions = draft?.versions?.length ? draft.versions : draft ? [draft] : [];
  const version = versions[selected];
  const snapshot = version?.task;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(version, null, 2)], { type: 'application/json;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url; link.download = `${snapshot.title || '任务'}-未同步草稿.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const restore = async () => {
    setBusy(true); setError('');
    try {
      await onCreateTask(recoveryTask(snapshot, `task:${crypto.randomUUID()}`));
      setOpen(false);
    } catch (failure) { setError(failure.message || '恢复失败，原草稿仍保留'); }
    finally { setBusy(false); }
  };
  if (!draft) return error ? <span role="alert">{error}</span> : null;
  return <>
    <button type="button" className="unified-header-action" onClick={() => setOpen(true)}>未同步草稿</button>
    {open && <div className="task-draft-backdrop"><section role="dialog" aria-modal="true" aria-label="恢复未同步草稿" className="task-draft-dialog theme-panel" onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false); }}>
      <div className="unified-pane-head"><strong>未同步草稿</strong><button type="button" autoFocus onClick={() => setOpen(false)}>关闭</button></div>
      <p>可复制为新任务，原任务和草稿会保留。</p>
      {drafts.length > 1 && <select aria-label="未同步任务" value={snapshot.id} onChange={(event) => {
        const next = drafts.find(item => item.task.id === event.target.value);
        setDraft(next); setSelected(Math.max(0, (next?.versions?.length || 1) - 1));
      }}>{drafts.map(item => <option key={item.task.id} value={item.task.id}>{item.task.title || '未命名任务'}</option>)}</select>}
      <select aria-label="草稿版本" value={selected} onChange={(event) => setSelected(Number(event.target.value))}>
        {versions.map((item, index) => <option key={index} value={index}>{new Date(item.savedAt).toLocaleString()} · 版本 {index + 1}</option>)}
      </select>
      <div className="task-draft-preview">
        <h3>{snapshot.title}</h3>
        <p>{snapshot.paperIds?.length || 0} 篇论文 · {snapshot.messages?.length || 0} 条对话</p>
        {(snapshot.messages || []).map((message, index) => <p key={`m${index}`}><strong>{message.role === 'user' ? '我' : '助手'}：</strong>{message.content}</p>)}
        {[...(snapshot.notes || []), ...(snapshot.artifacts || [])].map((item, index) => <div key={`d${index}`}><h4>{item.title || '笔记'}</h4><p>{item.text || item.content}</p></div>)}
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="unified-document-toolbar"><button type="button" disabled={busy} onClick={restore}>{busy ? '恢复中…' : '复制为新任务'}</button><button type="button" onClick={download}>下载备份</button></div>
    </section></div>}
  </>;
}
