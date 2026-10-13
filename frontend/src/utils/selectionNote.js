export function selectionNote(payload, paperId, id) {
  const original = payload?.text || payload?.content || '';
  const interpretation = payload?.aiInterpretation || '';
  const includeInterpretation = interpretation.trim() && !['解析中...', '边注已保存。',
    '已保存为边注，可继续补充自己的观察与问题。'].includes(interpretation.trim());
  return { id, title: '原文笔记', text: includeInterpretation ? `${original}\n\n## 阅读笔记\n\n${interpretation}` : original,
    paperIds: [paperId], source: payload, versions: [], createdAt: new Date().toISOString(),
    sources: [{ pdfId: paperId, sourceId: payload?.sourceAnchorId, sourceAnchorId: payload?.sourceAnchorId,
      pageIndex: payload?.sourcePageIndex ?? payload?.pageNumber, text: original }] };
}
