export const QUICK_PROMPTS = ['方法对比', '创新点总结', '局限性分析', '生成综述', '制定阅读计划'];

export const STAGE_LABELS = {
  planning: '规划中',
  retrieving: '检索中',
  synthesizing: '综合中',
  done: '已完成',
};

export const STATUS_LABELS = {
  succeeded: '已完成',
  running: '执行中',
  pending: '等待中',
  cancelled: '已取消',
  failed: '失败',
  fallback: '原型模式',
  done: '已完成',
};

export const STATUS_TONE = {
  succeeded: 'agent-status-succeeded',
  running: 'agent-status-running',
  pending: 'agent-status-pending',
  cancelled: 'agent-status-cancelled',
  failed: 'agent-status-failed',
  fallback: 'agent-status-fallback',
  done: 'agent-status-done',
};

export const TERMINAL_AGENT_STATUSES = new Set(['succeeded', 'failed', 'cancelled']);

export const formatRelativeMeta = (project) => {
  if (!project) return '等待创建项目';
  const paperCount = project.paperIds?.length || 0;
  const latestTask = project.latestTaskId ? '有最近任务' : '暂无任务';
  return `${paperCount} 篇论文 · ${latestTask}`;
};

export const getStatusTone = (status) => STATUS_TONE[`${status || ''}`.trim()] || STATUS_TONE.pending;

export const getStatusLabel = (status) => STATUS_LABELS[`${status || ''}`.trim()] || status || '等待中';

export const getProgressWidth = (progress) =>
  `${Math.max(0, Math.min(100, Math.round((progress || 0) * 100)))}%`;

export const formatAgentTime = (value) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};
