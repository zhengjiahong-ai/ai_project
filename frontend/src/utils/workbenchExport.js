const normalizeText = (value) => `${value ?? ''}`.trim();

const formatPageLabel = (pageIndex) => (Number.isFinite(pageIndex) && pageIndex >= 0 ? `p.${pageIndex + 1}` : '未定位页码');

const formatDate = (timestamp = Date.now()) => {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return '';
  }

  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
};

export const buildWorkbenchMarkdown = ({
  pdfFileName = '当前论文',
  cards = [],
  notes = [],
  laneLabels = {},
  kindLabels = {},
}) => {
  const cardGroups = cards.reduce((map, card) => {
    const lane = normalizeText(card?.lane) || 'inbox';
    if (!map[lane]) {
      map[lane] = [];
    }
    map[lane].push(card);
    return map;
  }, {});

  const lines = [
    `# 论文研读成果导出`,
    '',
    `- 论文：${pdfFileName || '当前论文'}`,
    `- 导出时间：${formatDate()}`,
    `- 工作台卡片：${cards.length}`,
    `- 边注：${notes.length}`,
    '',
    `## 一、卡片整理`,
    '',
  ];

  Object.entries(laneLabels).forEach(([laneKey, laneLabel]) => {
    const laneCards = cardGroups[laneKey] || [];
    lines.push(`### ${laneLabel}（${laneCards.length}）`);
    lines.push('');

    if (laneCards.length === 0) {
      lines.push('暂无内容');
      lines.push('');
      return;
    }

    laneCards.forEach((card, index) => {
      lines.push(`#### ${index + 1}. ${normalizeText(card.title) || '未命名卡片'}`);
      lines.push(`- 类型：${kindLabels[card.kind] || card.kind || '未分类'}`);
      lines.push(`- 页码：${formatPageLabel(card.pageIndex)}`);
      if (Array.isArray(card.tags) && card.tags.length > 0) {
        lines.push(`- 标签：${card.tags.join('、')}`);
      }
      lines.push('');
      lines.push(normalizeText(card.summary) || '暂无摘要');

      if (normalizeText(card.userNote)) {
        lines.push('');
        lines.push(`作者备注：${normalizeText(card.userNote)}`);
      }

      if (normalizeText(card.content)) {
        lines.push('');
        lines.push('详细内容：');
        lines.push(normalizeText(card.content));
      }

      lines.push('');
    });
  });

  lines.push('## 二、边注复盘');
  lines.push('');

  if (notes.length === 0) {
    lines.push('暂无边注');
    lines.push('');
  } else {
    notes.forEach((note, index) => {
      const pageIndex = Number.isFinite(note?.sourcePageIndex) ? note.sourcePageIndex : note?.pageNumber;
      lines.push(`### ${index + 1}. ${formatPageLabel(pageIndex)}`);
      lines.push('');
      lines.push(`原文片段：${normalizeText(note?.text) || '暂无原文片段'}`);
      lines.push('');
      lines.push(`理解记录：${normalizeText(note?.aiInterpretation) || '暂无解释'}`);
      lines.push('');
    });
  }

  return lines.join('\n');
};

export const buildWorkbenchJson = ({
  pdfFileName = '',
  cards = [],
  notes = [],
} = {}) =>
  JSON.stringify(
    {
      exportedAt: new Date().toISOString(),
      pdfFileName,
      stats: {
        cardCount: cards.length,
        noteCount: notes.length,
      },
      cards,
      notes,
    },
    null,
    2,
  );

export const buildWorkbenchPlainText = ({
  pdfFileName = '当前论文',
  cards = [],
  notes = [],
}) => {
  const lines = [
    `论文：${pdfFileName || '当前论文'}`,
    `导出时间：${formatDate()}`,
    `卡片数：${cards.length}`,
    `边注数：${notes.length}`,
    '',
    '卡片：',
  ];

  cards.forEach((card, index) => {
    lines.push(`${index + 1}. ${normalizeText(card.title) || '未命名卡片'} ｜ ${normalizeText(card.summary) || '暂无摘要'}`);
  });

  lines.push('');
  lines.push('边注：');

  notes.forEach((note, index) => {
    lines.push(`${index + 1}. ${normalizeText(note.text) || '暂无片段'} ｜ ${normalizeText(note.aiInterpretation) || '暂无解释'}`);
  });

  return lines.join('\n');
};
