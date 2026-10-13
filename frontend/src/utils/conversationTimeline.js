export const operationInput = record => record.request || record.input?.original || record.input || {};
export const operationQuestion = record => {
  const input = operationInput(record);
  return input.displayText || input.message || input.question || input.text || input.goal ||
    ({ hint: '给我一个提示', pause: '暂停学习', resume: '继续学习', finish: '结束学习', skip: '跳过这个问题', retry: '重新回答', remediate: '补充前置知识', answer: '回答学习问题', ask: '临时追问' }[input.action]) || '处理请求';
};
const timeOf = value => {
  if (value === null || value === undefined) return null;
  const time = typeof value === 'number' ? value : Date.parse(value);
  return Number.isFinite(time) ? time : null;
};

/** Presentation only. Results are grouped with their original submission, not their completion time. */
export function conversationTimeline(task, records = {}) {
  if (!task) return [];
  const ops = Object.values(records).filter(record => record.taskId === task.id);
  const byRequest = new Map(ops.map(record => [record.requestId, record]));
  const retryParents = new Map(ops.filter(record => record.retriedBy).map(record => [record.retriedBy, record.requestId]));
  const originalRequest = record => {
    const seen = new Set();
    while (record && !seen.has(record.requestId)) {
      seen.add(record.requestId);
      const parent = byRequest.get(record.retryOf || retryParents.get(record.requestId));
      if (!parent) break;
      record = parent;
    }
    return record;
  };
  const latestRequest = record => {
    const seen = new Set();
    while (record?.retriedBy && !seen.has(record.requestId) && byRequest.has(record.retriedBy)) {
      seen.add(record.requestId); record = byRequest.get(record.retriedBy);
    }
    return record;
  };
  const requestIds = record => ops.filter(item => originalRequest(item)?.requestId === originalRequest(record)?.requestId).map(item => item.requestId);
  const userRequests = new Set();
  const runs = task.researchRuns || [];
  const byResearch = new Map(runs.map(run => [run.researchId, run]));
  const entries = (task.messages || []).flatMap((message, index) => {
    // The persisted research answer remains intact; its unified report card is rendered at the question.
    if (message.sourceResearchId && message.role !== 'user' && byResearch.has(message.sourceResearchId)) return [];
    const record = byRequest.get(message.sourceRequestId);
    const original = originalRequest(record);
    const run = byResearch.get(message.sourceResearchId);
    if (message.role === 'user' && original && userRequests.has(original.requestId)) return [];
    if (message.role === 'user' && original) userRequests.add(original.requestId);
    return [{ ...message, originalIndex: index,
      ...(record ? { timelineRootRequestId: original.requestId, timelineRequestIds: requestIds(record) } : {}),
      ...(message.role === 'user' && record ? { id: `${original.requestId}:user`, timelineOperationId: latestRequest(original).requestId } : {}),
      ...(message.role === 'user' && run ? { timelineResearchId: run.researchId } : {}),
      orderTime: timeOf(run?.createdAt) ?? timeOf(original?.createdAt) ?? timeOf(message.timestamp), orderIndex: index }];
  });
  for (let index = 0; index < entries.length; index++) {
    if (entries[index].orderTime !== null) continue;
    const before = entries.slice(0, index).findLast(entry => entry.orderTime !== null);
    const after = entries.slice(index + 1).find(entry => entry.orderTime !== null);
    entries[index].orderTime = before ? before.orderTime + 0.01 : after ? after.orderTime - (entries.length - index) * 0.01 : index;
  }
  for (const record of ops) {
    const original = originalRequest(record);
    if (record.retriedBy || record.kind === 'research.start' && runs.some(run => run.requestId === record.requestId)
      || entries.some(message => message.timelineRootRequestId === original.requestId)) continue;
    if (record.status === 'succeeded') continue;
    entries.push({ id: `${original.requestId}:user`, role: 'user', content: operationQuestion(original), synthetic: true,
      sourceRequestId: record.requestId, timelineOperationId: record.requestId, timelineRootRequestId: original.requestId, timelineRequestIds: requestIds(record),
      orderTime: timeOf(original.createdAt) ?? entries.length, orderIndex: entries.length });
  }
  for (const run of runs) {
    if (entries.some(message => message.timelineResearchId === run.researchId)) continue;
    entries.push({ id: `research:${run.researchId}:question`, role: 'user', content: run.question || '研究论文',
      sourceResearchId: run.researchId, sourceRequestId: run.requestId, timelineResearchId: run.researchId, synthetic: true,
      orderTime: timeOf(run.createdAt) ?? entries.length, orderIndex: entries.length });
  }
  return entries.sort((a, b) => a.orderTime - b.orderTime || a.orderIndex - b.orderIndex);
}

export function documentMessageIndex(task, document) {
  return (task.messages || []).findIndex(message =>
    document.sourceMessageId !== undefined && message.id === document.sourceMessageId ||
    document.sourceRequestId && message.sourceRequestId === document.sourceRequestId ||
    document.sourceResearchId && message.sourceResearchId === document.sourceResearchId ||
    message.artifactId && message.artifactId === (document.id || document.artifactId));
}
