const STORAGE_KEY = 'pixiu-agent-workspace';

export const loadAgentWorkspaceSnapshot = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    return {
      ...parsed,
      tasksByProjectId: parsed.tasksByProjectId && typeof parsed.tasksByProjectId === 'object'
        ? parsed.tasksByProjectId
        : {},
    };
  } catch {
    return null;
  }
};

export const saveAgentWorkspaceSnapshot = (snapshot) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // Ignore persistence errors in the first iteration.
  }
};
