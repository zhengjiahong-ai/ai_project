export const operationStatusLabels = { queued: '等待处理', running: '正在处理', unknown: '正在确认结果', cancelling: '正在停止',
  awaiting_submission: '提交未确认', failed: '未完成', interrupted: '处理已中断', cancelled: '已停止', conflicted: '结果已生成，请核对任务', succeeded: '已完成' };

export { operationQuestion } from '../utils/conversationTimeline';

export function operationStatusText(record) {
  if (record.status === 'running') return record.kind?.startsWith('learning.') ? '正在准备学习反馈…' : '正在分析论文…';
  if (record.status === 'unknown' || record.status === 'awaiting_submission') return '暂时无法确认结果';
  if (record.status === 'failed') return '处理未完成';
  return operationStatusLabels[record.status] || '正在确认状态';
}

export function operationFailureSummary(record) {
  if (!['failed', 'interrupted'].includes(record.status)) return '';
  const firstLine = String(record.error || '').split(/[\r\n]/u)[0].trim();
  return /[\u4e00-\u9fff]/u.test(firstLine) && firstLine.length <= 90 ? firstLine : '本次处理未完成，问题和已有记录仍保留。';
}

export function researchTitle(run, result, compactTitle) {
  const title = compactTitle || result?.title || result?.reportTitle || run.title || '论文研究';
  const line = String(title).replace(/\s+/gu, ' ').trim();
  return line.length > 32 ? `${line.slice(0, 32)}…` : line;
}

