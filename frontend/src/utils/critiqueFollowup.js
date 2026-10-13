export const critiqueVersion = artifact => String(artifact.updatedAt || artifact.createdAt || '');
export const critiqueMessageIsCurrent = (artifact, message) => !artifact?.sourceRequestId || !message?.sourceRequestId
  || artifact.sourceRequestId === message.sourceRequestId;

export function resolveCritiqueFollowup(task, text, selection) {
  if (selection?.taskId === task.id) return selection.followup;
  const match = text.match(/(?:第([一二三四五六七八九十\d]+)点|展开(?:实验条件|这一点)|解释(?:一下)?(?:这一点|这点)|把(?:这个|这点)转成实验方案)/u);
  if (!match) return null;
  const message = (task.messages || []).findLast(item => item.role !== 'user' && item.critique?.schemaVersion === 2);
  if (!message) return null;
  const artifact = (task.artifacts || []).find(item => (item.id || item.artifactId) === message.artifactId
    || message.id && item.sourceMessageId === message.id || item.sourceRequestId && item.sourceRequestId === message.sourceRequestId);
  if (!artifact?.critique || !critiqueVersion(artifact)) return null;
  if (!critiqueMessageIsCurrent(artifact, message)) return { error: '这条回答对应旧版本，请打开成果查看当前判断，或在历史版本中找回原记录。' };
  const ordinal = match[1] && (/^\d+$/u.test(match[1]) ? Number(match[1]) : '一二三四五六七八九十'.indexOf(match[1]) + 1);
  const issueId = ordinal ? message.critique.presentation?.chatIssueIds?.[ordinal - 1] : undefined;
  if (ordinal && !issueId) return null;
  return { artifactId: artifact.id || artifact.artifactId, version: critiqueVersion(artifact), ...(issueId ? { issueId } : {}) };
}
