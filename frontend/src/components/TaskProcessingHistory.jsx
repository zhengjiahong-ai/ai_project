import React, { useState } from 'react';
import { OperationRecord } from './ConversationExecution';
import { ResearchCard } from './ConversationResearch';
import { researchTitle, operationQuestion, operationStatusLabels } from './conversationProcessingModel';
import { getResearchStatusMeta } from './deepResearchPanelModel';

export default function TaskProcessingHistory({ task, records = {}, research = {}, onLocateOperation, onLocateResearch,
  onRetry, onSubmitSaved, onRefresh, onCancel, onOpenResult, onOpenReport, busy, queryError }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const operations = Object.values(records).filter(record => record.taskId === task.id
    && !(record.kind === 'research.start' && task.researchRuns?.some(run => run.requestId === record.requestId))).map(record => ({
    key: `operation-${record.requestId}`, type: 'operation', record, status: record.status,
    title: operationQuestion(record) || record.kind || '处理请求', date: record.updatedAt || record.createdAt || '',
  }));
  const runs = (task.researchRuns || []).map(run => {
    const result = research.runs?.[`${task.id}/${run.researchId}`] || (task.artifacts?.some(item => item.sourceResearchId === run.researchId || (item.id || item.artifactId) === `research:${run.researchId}:artifact`) ? { status: 'succeeded' } : null);
    const savedTitle = task.artifacts?.find(item => item.sourceResearchId === run.researchId || (item.id || item.artifactId) === `research:${run.researchId}:artifact`)?.title;
    return { key: `research-${run.researchId}`, type: 'research', run, result,
      status: result?.status || run.status || 'unknown', title: researchTitle(run, result, savedTitle),
      date: result?.updatedAt || run.updatedAt || run.createdAt || '' };
  });
  const entries = [...operations, ...runs].sort((a, b) => String(b.date).localeCompare(String(a.date)));
  const matches = entries.filter(entry => (status === 'all' || entry.status === status) &&
    [entry.title, entry.run?.question, entry.record?.error, entry.result?.error].filter(Boolean).join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const labelFor = entry => entry.type === 'operation' ? operationStatusLabels[entry.status] || entry.status : getResearchStatusMeta(entry.status, entry.result?.outcome).label;
  const states = Array.from(new Set(entries.map(entry => entry.status)));
  return <section aria-label="任务处理记录" className="task-processing-history">
    {queryError && <details><summary>部分请求记录暂不可读取</summary><p>{queryError}。以下仅显示已读取或本地保留的记录。</p><button type="button" onClick={onRefresh}>查询状态</button></details>}
    <div className="flex flex-wrap items-center gap-2 py-2">
      <input className="theme-input min-w-0 flex-1 rounded px-2 py-1" aria-label="搜索处理记录" placeholder="搜索处理记录" value={query} onChange={event => setQuery(event.target.value)} />
      <select className="theme-input rounded px-2 py-1" aria-label="处理状态筛选" value={status} onChange={event => setStatus(event.target.value)}>
        <option value="all">全部状态</option>
        {states.map(value => <option key={value} value={value}>{labelFor(entries.find(entry => entry.status === value))}</option>)}
      </select>
    </div>
    <p className="theme-text-muted text-xs">{matches.length} 条处理记录</p>
    {!matches.length && <p className="theme-text-muted text-sm">没有匹配的处理记录</p>}
    {matches.map(entry => <article key={entry.key} className="theme-card-soft my-2 rounded-lg p-2" data-processing-id={entry.key}>
      <div className="flex min-w-0 items-center gap-2">
        <span className="theme-text-muted text-xs">{entry.type === 'research' ? '研究' : '请求'}</span>
        <button className="min-w-0 truncate text-left text-sm" type="button" title={entry.type === 'research' ? entry.run.question : entry.title}
          disabled={entry.type === 'research' ? !onLocateResearch : !onLocateOperation}
          onClick={() => entry.type === 'research' ? onLocateResearch?.(entry.run) : onLocateOperation?.(entry.record)}>{entry.title}</button>
      </div>
      {entry.type === 'operation' ? <OperationRecord record={entry.record} showQuestion={false} busy={busy} onRetry={onRetry} onSubmitSaved={onSubmitSaved}
        onRefresh={onRefresh} onCancel={onCancel} onOpenResult={onOpenResult} onLocate={onLocateOperation} />
        : <ResearchCard taskId={task.id} run={entry.run} result={entry.result} compactTitle={entry.title} error={research.errors?.[JSON.stringify([task.id, entry.run.researchId])]} onRefresh={research.refresh} onAction={research.action} onOpenReport={onOpenReport} />}
    </article>)}
  </section>;
}
