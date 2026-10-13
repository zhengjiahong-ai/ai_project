import React, { useState } from 'react';
import { operationStatusLabels, operationStatusText, operationFailureSummary, operationQuestion } from './conversationProcessingModel';
import WorkbenchPopover from './WorkbenchPopover';

const activeStatuses = new Set(['queued', 'running', 'unknown', 'cancelling']);
/** Controls operate on the saved request ID; unconfirmed requests are queried first. */
export function OperationRecord({ record, busy, showQuestion = true, onRetry, onSubmitSaved, onRefresh, onCancel, onOpenResult, onLocate }) {
  const [actionError, setActionError] = useState('');
  const question = operationQuestion(record);
  const text = record.result?.artifact?.text || record.result?.message || record.result?.reply;
  const invoke = (handler, ...args) => {
    if (!handler) return;
    setActionError('');
    try { Promise.resolve(handler(...args)).catch(error => setActionError(error?.message || '操作未完成，请重试。')); }
    catch (error) { setActionError(error?.message || '操作未完成，请重试。'); }
  };
  return <div className="unified-execution-row" data-request-id={record.requestId} data-status={record.status}>
    <span role="status" className="unified-execution-status"><span className="unified-execution-dot" aria-hidden="true" />{operationStatusText(record)}</span>
    {operationFailureSummary(record) && <span className="unified-execution-reason">{operationFailureSummary(record)}</span>}
    {showQuestion && question && <span className="unified-execution-question" title={question}>{question}</span>}
    <div className="unified-execution-actions">
    {record.retriedBy ? <span>已由后续请求接续</span> : record.status === 'succeeded'
      ? onLocate && <button type="button" onClick={() => invoke(onLocate, record)}>打开对应对话</button>
      : record.status === 'awaiting_submission'
      ? <><button type="button" disabled={!onRefresh} onClick={() => invoke(onRefresh)}>查询状态</button><button type="button" disabled={busy || !onSubmitSaved} onClick={() => invoke(onSubmitSaved, record.requestId)}>继续发送</button><button type="button" disabled={!onCancel} onClick={() => invoke(onCancel, record.requestId)}>停止</button></>
      : activeStatuses.has(record.status)
      ? <>{record.status === 'unknown' && <button type="button" onClick={() => invoke(onRefresh)} disabled={!onRefresh}>查询状态</button>}
        <button type="button" disabled={record.status === 'cancelling' || !onCancel} onClick={() => invoke(onCancel, record.requestId)}>{record.status === 'cancelling' ? '停止中' : '停止'}</button>
        {record.status !== 'unknown' && onRefresh && <WorkbenchPopover label="请求更多操作">
          {close => <button type="button" onClick={() => { invoke(onRefresh); close(); }}>查询状态</button>}
        </WorkbenchPopover>}</>
      : record.status !== 'conflicted' && <button type="button" disabled={busy || !record.request || !onRetry} onClick={() => invoke(onRetry, record.requestId)}>重试</button>}
    {record.status === 'conflicted' && text && <button type="button" disabled={!onOpenResult} onClick={() => invoke(onOpenResult, record)}>打开已生成结果</button>}
    </div>
    {record.error && <details><summary>详情</summary><p>{record.error}</p></details>}
    {actionError && <p role="alert">{actionError}</p>}
  </div>;
}

/** Legacy compact recovery list; successful records are available in task history. */
export default function ConversationExecution({ task, records = {}, ...actions }) {
  const visible = Object.values(records).filter(record => record.taskId === task.id && !record.retriedBy && record.status !== 'succeeded');
  const active = visible.filter(record => activeStatuses.has(record.status));
  const completed = visible.filter(record => !activeStatuses.has(record.status) && operationStatusLabels[record.status])
    .sort((a, b) => String(b.updatedAt || b.createdAt || '').localeCompare(String(a.updatedAt || a.createdAt || '')));
  const renderRecord = record => <OperationRecord key={record.requestId} record={record} {...actions} />;
  if (!active.length && !completed.length) return null;
  return <div className="unified-execution" aria-label="处理与恢复">
    {active.map(renderRecord)}
    {completed.slice(0, 1).map(renderRecord)}
    {completed.length > 1 && <details><summary>其他未完成请求（{completed.length - 1}）</summary>{completed.slice(1).map(renderRecord)}</details>}
  </div>;
}
