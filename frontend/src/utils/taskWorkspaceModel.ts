export type TaskWorkspace = {
  id: string;
  title: string;
  archived?: boolean;
  paperIds: string[];
  messages: unknown[];
  notes: unknown[];
  artifacts: unknown[];
  focusedPaperId: string | null;
  activeActivity: TaskActivity | null;
  revision?: number;
  activityHistory?: TaskActivity[];
  researchRuns?: { researchId: string; paperIds: string[]; primaryPaperId?: string; question?: string }[];
  appliedRequestIds?: string[];
  updatedAt: string;
};

export type TaskActivity = {
  id?: string;
  activityId?: string;
  taskId?: string;
  pdfId?: string;
  revision?: number;
  status?: string;
  paperIds?: string[];
  primaryPaperId?: string | null;
  strictScope?: boolean;
  snapshot?: {
    paperIds?: string[];
    primaryPaperId?: string | null;
    strictScope?: boolean;
  };
};

export type ContextRequest = {
  paperIds?: string[];
  text?: string;
  focusedPaperId?: string | null;
  activity?: TaskActivity | null;
  strictScope?: boolean;
};

export type ResolvedTaskContext = {
  taskId: string;
  allowedPaperIds: string[];
  primaryPaperId: string | null;
  strictScope: boolean;
  activityId?: string;
};

const SINGLE_PAPER_REFERENCE = /(?:这篇|本文|此文|该文|这篇论文|该论文|它的(?:方法|实验|结论|贡献|局限)|this paper|the paper)/iu;
const STRICT_REFERENCE = /(?:只根据|仅根据|只用|仅用|只看|仅看|限于|限定于|only\s+(?:use|based on|according to))/iu;
const WHOLE_TASK_REFERENCE = /(?:任务(?:中|内|里)?(?:的)?(?:全部|所有)?(?:论文|材料)|这些论文|所有论文|全部论文)/u;

function uniquePaperIds(paperIds: string[], taskPaperIds: string[]): string[] {
  const allowed = new Set(taskPaperIds);
  const result: string[] = [];
  for (const paperId of paperIds) {
    if (typeof paperId !== 'string' || !allowed.has(paperId)) {
      throw new Error(`论文不属于当前任务：${String(paperId)}`);
    }
    if (!result.includes(paperId)) result.push(paperId);
  }
  return result;
}

/** Resolve a request against one task. Never expands an empty task to the global library. */
export function resolveTaskContext(task: TaskWorkspace, request: ContextRequest = {}): ResolvedTaskContext {
  if (!task?.id || !Array.isArray(task.paperIds)) {
    throw new Error('任务数据无效');
  }

  const taskPaperIds = uniquePaperIds(task.paperIds, task.paperIds);
  const focus = request.focusedPaperId === undefined ? task.focusedPaperId : request.focusedPaperId;
  if (focus != null && !taskPaperIds.includes(focus)) {
    throw new Error(`阅读焦点不属于当前任务：${focus}`);
  }

  const strict = Boolean(request.strictScope || STRICT_REFERENCE.test(request.text || ''));
  if (request.paperIds !== undefined) {
    if (!Array.isArray(request.paperIds)) throw new Error('指定论文必须是数组');
    const explicitIds = uniquePaperIds(request.paperIds, taskPaperIds);
    return {
      taskId: task.id,
      allowedPaperIds: explicitIds,
      primaryPaperId: explicitIds[0] ?? null,
      strictScope: strict,
    };
  }

  if (strict) {
    if (WHOLE_TASK_REFERENCE.test(request.text || '')) {
      return { taskId: task.id, allowedPaperIds: taskPaperIds, primaryPaperId: taskPaperIds.length === 1 ? taskPaperIds[0] : null, strictScope: true };
    }
    if (!focus && taskPaperIds.length > 1) {
      throw new Error('请明确指定只使用哪篇论文');
    }
    const selected = focus ?? taskPaperIds[0] ?? null;
    return {
      taskId: task.id,
      allowedPaperIds: selected ? [selected] : [],
      primaryPaperId: selected,
      strictScope: true,
    };
  }

  if (WHOLE_TASK_REFERENCE.test(request.text || '')) {
    return { taskId: task.id, allowedPaperIds: taskPaperIds,
      primaryPaperId: taskPaperIds.length === 1 ? taskPaperIds[0] : null, strictScope: false };
  }

  const activity = request.activity === undefined ? task.activeActivity : request.activity;
  if (activity && activity.status !== 'finished') {
    const snapshot = activity.snapshot ?? activity;
    const activityPaperIds = uniquePaperIds(snapshot.paperIds ?? [], taskPaperIds);
    const primaryPaperId = snapshot.primaryPaperId ?? activityPaperIds[0] ?? null;
    if (primaryPaperId && !activityPaperIds.includes(primaryPaperId)) {
      throw new Error(`活动主论文不在活动材料范围内：${primaryPaperId}`);
    }
    return {
      taskId: task.id,
      allowedPaperIds: activityPaperIds,
      primaryPaperId,
      strictScope: Boolean(snapshot.strictScope ?? activity.strictScope),
      ...((activity.activityId || activity.id) ? { activityId: activity.activityId || activity.id } : {}),
    };
  }

  const singleReference = SINGLE_PAPER_REFERENCE.test(request.text || '');
  if (singleReference && !focus && taskPaperIds.length > 1) {
    throw new Error('请明确指定当前指的是哪篇论文');
  }
  return {
    taskId: task.id,
    allowedPaperIds: taskPaperIds,
    primaryPaperId: singleReference ? (focus ?? taskPaperIds[0] ?? null) : (taskPaperIds.length === 1 ? taskPaperIds[0] : null),
    strictScope: false,
  };
}
