type Activity = { activityId?: string; id?: string; revision?: number; status?: string; [key: string]: unknown };

/** Stored revisions remain intact; navigation lists one saved record per activity. */
export function learningActivityHistory(task?: { activityHistory?: Activity[]; activeActivity?: Activity | null } | null): Activity[] {
  const current = task?.activeActivity;
  const currentId = current?.activityId || current?.id;
  const grouped = new Map<string, Activity>();
  for (const [index, activity] of (task?.activityHistory || []).entries()) {
    const id = activity.activityId || activity.id || `legacy:${index}`;
    if (id === currentId && current?.status !== 'finished') continue;
    const previous = grouped.get(id);
    if (!previous || (activity.revision || 0) >= (previous.revision || 0)) grouped.set(id, activity);
  }
  if (currentId && ['finished', 'paused'].includes(`${current?.status}`)) grouped.set(currentId, current);
  return [...grouped.values()];
}
