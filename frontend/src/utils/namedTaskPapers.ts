type Paper = { id: string; title?: string; filename?: string };

/** Resolve explicit names before focus/activity heuristics. Never imports library papers. */
export function resolveNamedTaskPapers(text: string, papers: Paper[], taskPaperIds: string[]): string[] | undefined {
  const requested: string[] = [];
  const allowed = new Set(taskPaperIds);
  const addMatches = (name: string, exact: boolean) => {
    const byId = exact ? papers.find(paper => paper.id === name) : undefined;
    const matches = byId ? [byId] : papers.filter((paper) => [paper.id, paper.title, paper.filename]
      .some((label) => label && (exact ? label === name : label.length >= 4 && name.includes(label))));
    if (exact && matches.length === 0) throw new Error(`找不到指定论文：${name}`);
    if (exact && matches.length > 1) throw new Error(`有多篇同名论文，请使用论文 ID 指定：${name}`);
    for (const paper of matches) {
      if (!allowed.has(paper.id)) throw new Error(`论文不属于当前任务：${paper.title || paper.id}`);
      if (!requested.includes(paper.id)) requested.push(paper.id);
    }
  };
  // Braces allow IDs or titles containing spaces without swallowing the question.
  const mentions = [...text.matchAll(/@\{([^}]+)\}|《([^》]+)》|(?:^|\s)@([^{}@\s]+)/gu)];
  if (mentions.length) {
    for (const match of mentions) addMatches((match[1] || match[2] || match[3]).trim(), true);
  } else {
    addMatches(text, false);
  }
  return requested.length ? requested : undefined;
}
