/** Pure utility functions extracted from App.jsx — outline, formatting, error handling. */

import React from 'react';

export const sectionDisplayNames = {
  abstract: '摘要',
  introduction: '1 Introduction',
  methods: '3 Methodology',
  results: '4 Experiments',
  discussion: '5 Discussion',
  conclusion: '6 Conclusion',
};

export const outlineSourceLabels = {
  pdf: 'PDF结构',
  tei: 'PDF结构',
  layout: '版面补全',
  'pdf-layout': 'PDF行补全',
  'tei+layout': 'PDF+版面',
  inferred: '推断结构',
  aiStructure: 'AI解析',
  aiSkeleton: 'AI目录',
  pending: '待解析',
};

export const normalizeBackgroundKnowledgeLevel = (value) => {
  const text = `${value ?? ''}`.trim().toLowerCase();
  if (['入门', 'beginner', 'novice', '基础'].includes(text)) {
    return '入门';
  }
  if (['进阶', 'advanced', 'expert', '深入'].includes(text)) {
    return '进阶';
  }
  return '一般';
};

export const normalizeReaderTagList = (value) => {
  if (Array.isArray(value)) {
    return [...new Set(value.map((item) => `${item ?? ''}`.trim()).filter(Boolean))];
  }
  if (typeof value === 'string') {
    return [...new Set(
      value
        .split(/[\n,，;；、]/)
        .map((item) => item.trim())
        .filter(Boolean),
    )];
  }
  return [];
};

export const coerceFiniteNumber = (value) => {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

export const getOutlineLevel = (label) => {
  const text = `${label || ''}`.trim();
  const numberMatch = text.match(/^\s*(?:section\s+)?(\d+(?:\.\d+)*)(?:[.)])?\s*/i);
  if (!numberMatch) {
    return 1;
  }
  return Math.min(4, Math.max(1, numberMatch[1].split('.').filter(Boolean).length));
};

export const getOutlinePageLabel = (page, pageIndex) => {
  if (Number.isFinite(page) && page > 0) {
    return `p.${page}`;
  }
  if (Number.isFinite(pageIndex)) {
    return `p.${pageIndex + 1}`;
  }
  return '';
};

export const normalizeOutlinePage = (section) => {
  const pageIndex = coerceFiniteNumber(section?.pageIndex);
  const page = coerceFiniteNumber(section?.page);
  const resolvedPageIndex = Number.isFinite(pageIndex)
    ? pageIndex
    : Number.isFinite(page)
      ? Math.max(0, page - 1)
      : null;
  const resolvedPage = Number.isFinite(page)
    ? page
    : Number.isFinite(resolvedPageIndex)
      ? resolvedPageIndex + 1
      : null;

  return {
    page: resolvedPage,
    pageIndex: resolvedPageIndex,
    pageLabel: getOutlinePageLabel(resolvedPage, resolvedPageIndex),
  };
};

export const flattenOutlineHierarchy = (rawItems) => {
  const validItems = rawItems.filter((item) => `${item.label || ''}`.trim());
  if (validItems.length === 0) {
    return [];
  }

  const minLevel = Math.min(...validItems.map((item) => item.level || getOutlineLevel(item.label)));
  const stack = [];
  const seenIds = new Map();
  const idAliases = new Map();

  const normalizedItems = validItems.map((item, index) => {
    const baseLevel = item.level || getOutlineLevel(item.label);
    const level = Math.min(4, Math.max(1, baseLevel - minLevel + 1));
    const baseId = `${item.id || `outline-${index + 1}`}`.trim() || `outline-${index + 1}`;
    const duplicateCount = seenIds.get(baseId) || 0;
    const id = duplicateCount ? `${baseId}-${duplicateCount + 1}` : baseId;
    seenIds.set(baseId, duplicateCount + 1);
    idAliases.set(baseId, id);

    return {
      ...item,
      id,
      level,
      sourceParentId: item.parentId ? `${item.parentId}` : null,
    };
  });

  const itemById = new Map(normalizedItems.map((item) => [item.id, item]));

  const itemsWithParents = normalizedItems.map((item) => {
    const explicitParentId = idAliases.get(item.sourceParentId) || item.sourceParentId;
    let parent = explicitParentId && itemById.has(explicitParentId) ? itemById.get(explicitParentId) : null;

    if (!parent) {
      while (stack.length > 0 && stack[stack.length - 1].level >= item.level) {
        stack.pop();
      }
      parent = stack[stack.length - 1] || null;
    }

    const nextItem = {
      ...item,
      parentId: parent?.id || null,
    };

    stack.push(nextItem);
    return nextItem;
  });

  const resolvedItemsById = new Map(itemsWithParents.map((item) => [item.id, item]));
  const resolveAncestorIds = (item, visitedIds = new Set()) => {
    if (!item.parentId || visitedIds.has(item.parentId)) {
      return [];
    }
    const parent = resolvedItemsById.get(item.parentId);
    if (!parent) {
      return [];
    }
    visitedIds.add(item.parentId);
    return [...resolveAncestorIds(parent, visitedIds), parent.id];
  };

  const childCountByParent = itemsWithParents.reduce((countMap, item) => {
    if (item.parentId) {
      countMap.set(item.parentId, (countMap.get(item.parentId) || 0) + 1);
    }
    return countMap;
  }, new Map());

  return itemsWithParents.map((item) => ({
    ...item,
    ancestorIds: resolveAncestorIds(item),
    hasChildren: childCountByParent.has(item.id),
    childCount: childCountByParent.get(item.id) || 0,
  }));
};

export const buildPaperOutlineModel = (deconstructData) => {
  const structure = deconstructData?.paper_structure;
  const skeleton = deconstructData?.paper_skeleton;

  if (Array.isArray(structure?.sections) && structure.sections.length > 0) {
    const items = structure.sections.map((section, index) => {
      const label = `${
        section.displayTitle
        || section.title
        || section.name
        || section.section
        || `Section ${index + 1}`
      }`.trim();
      const pageMeta = normalizeOutlinePage(section);
      const explicitLevel = coerceFiniteNumber(section.level ?? section.nestedLevel);
      const headingNumber = `${section.headingNumber || section.number || ''}`.trim();
      const itemSource = section.source || 'pdf';

      return {
        id: section.id || section.key || `section-${index + 1}`,
        label,
        rawTitle: section.rawTitle || label,
        level: Number.isFinite(explicitLevel)
          ? explicitLevel
          : getOutlineLevel(headingNumber || label),
        parentId: section.parentId || null,
        headingNumber,
        meta: pageMeta.pageLabel || section.type || `${index + 1}`,
        preview: section.preview || section.summary || '',
        source: itemSource,
        sourceLabel: outlineSourceLabels[itemSource] || outlineSourceLabels.pdf,
        confidence: coerceFiniteNumber(section.confidence),
        bbox: section.bbox || null,
        anchorY: coerceFiniteNumber(section.anchorY),
        ...pageMeta,
      };
    });

    return {
      source: 'pdf',
      sourceLabel: outlineSourceLabels.pdf,
      items: flattenOutlineHierarchy(items),
    };
  }

  if (structure && typeof structure === 'object' && !Array.isArray(structure)) {
    const structureItems = [
      ['research_problem', '研究问题'],
      ['core_hypothesis', '核心假设'],
      ['method_framework', '方法框架'],
      ['claimed_contributions', '主要贡献'],
      ['experimental_logic', '实验逻辑'],
      ['limitations', '局限性'],
    ]
      .filter(([key]) => {
        const value = structure[key];
        return Array.isArray(value) ? value.length > 0 : Boolean(`${value || ''}`.trim());
      })
      .map(([key, label], index) => ({
        id: key,
        label,
        level: 1,
        meta: `${index + 1}`,
        preview: Array.isArray(structure[key]) ? structure[key].join(' ') : structure[key],
        source: 'aiStructure',
        page: null,
        pageIndex: null,
        pageLabel: '',
      }));

    if (structureItems.length > 0) {
      return {
        source: 'aiStructure',
        sourceLabel: outlineSourceLabels.aiStructure,
        items: flattenOutlineHierarchy(structureItems),
      };
    }
  }

  if (skeleton && typeof skeleton === 'object') {
    const items = Object.keys(sectionDisplayNames)
      .filter((key) => {
        const value = skeleton[key];
        return typeof value === 'string' && value.trim() && !value.includes('请提供具体内容');
      })
      .map((key, index) => ({
        id: key,
        label: sectionDisplayNames[key] || key,
        level: getOutlineLevel(sectionDisplayNames[key] || key),
        meta: `${index + 1}`,
        preview: skeleton[key],
        source: 'aiSkeleton',
        page: null,
        pageIndex: null,
        pageLabel: '',
      }));

    return {
      source: 'aiSkeleton',
      sourceLabel: outlineSourceLabels.aiSkeleton,
      items: flattenOutlineHierarchy(items),
    };
  }

  return {
    source: 'pending',
    sourceLabel: outlineSourceLabels.pending,
    items: [],
  };
};

export const getVisibleOutlineItems = (items, collapsedIds, query) => {
  const normalizedQuery = `${query || ''}`.trim().toLowerCase();
  if (!normalizedQuery) {
    return items.filter((item) => !item.ancestorIds.some((ancestorId) => collapsedIds[ancestorId]));
  }
  const visibleIds = new Set();
  items.forEach((item) => {
    const searchableText = [
      item.label, item.rawTitle, item.headingNumber, item.meta, item.pageLabel, item.preview,
    ].filter(Boolean).join(' ').toLowerCase();
    if (searchableText.includes(normalizedQuery)) {
      visibleIds.add(item.id);
      item.ancestorIds.forEach((ancestorId) => visibleIds.add(ancestorId));
    }
  });
  return items.filter((item) => visibleIds.has(item.id));
};

export const resolveCurrentOutlineItem = (items, currentPageIndex) => {
  if (!Number.isFinite(currentPageIndex)) {
    return null;
  }
  return items.reduce((currentItem, item) => {
    if (!Number.isFinite(item.pageIndex) || item.pageIndex > currentPageIndex) {
      return currentItem;
    }
    if (!currentItem || item.pageIndex >= currentItem.pageIndex) {
      return item;
    }
    return currentItem;
  }, null);
};

export const renderHighlightedText = (text, query) => {
  const rawText = `${text || ''}`;
  const normalizedQuery = `${query || ''}`.trim();
  if (!normalizedQuery) {
    return rawText;
  }
  const lowerText = rawText.toLowerCase();
  const lowerQuery = normalizedQuery.toLowerCase();
  const parts = [];
  let cursor = 0;
  let matchIndex = lowerText.indexOf(lowerQuery, cursor);

  while (matchIndex >= 0) {
    if (matchIndex > cursor) {
      parts.push(rawText.slice(cursor, matchIndex));
    }
    const matchedText = rawText.slice(matchIndex, matchIndex + normalizedQuery.length);
    parts.push(
      React.createElement('mark', { key: `${matchIndex}-${matchedText}`, className: 'outline-search-mark' }, matchedText),
    );
    cursor = matchIndex + normalizedQuery.length;
    matchIndex = lowerText.indexOf(lowerQuery, cursor);
  }
  if (cursor < rawText.length) {
    parts.push(rawText.slice(cursor));
  }
  return parts;
};

export const normalizeAuthors = (authors) => {
  if (Array.isArray(authors)) {
    return authors.filter(Boolean).join(', ');
  }
  return `${authors || ''}`.trim();
};

export const clampSnippet = (text, maxLength = 96) => {
  const normalized = `${text || ''}`.replace(/\s+/g, ' ').trim();
  if (!normalized) return '';
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized;
};

export const formatUploadErrorMessage = (error) => {
  const responseMessage = error?.response?.data?.message || error?.response?.data?.detail;
  if (responseMessage) return responseMessage;
  if (error?.message === 'Network Error' || error?.code === 'ERR_NETWORK') {
    return '无法连接后端服务。请确认 Docker Desktop 已启动，并且 Java 网关 http://localhost:8081/api 正在运行。';
  }
  return error?.message || '上传失败，请确认后端服务已启动。';
};

const getCriticalReadingErrorBody = (error) => {
  const responseBody = error?.response?.data;
  if (responseBody && typeof responseBody === 'object') return responseBody;
  const payload = error?.payload;
  if (payload && typeof payload === 'object') return payload;
  return {};
};

export const getCriticalReadingErrorCode = (error) => {
  const body = getCriticalReadingErrorBody(error);
  const analysis = body?.analysis && typeof body.analysis === 'object' ? body.analysis : {};
  return error?.code || body?.errorCode || analysis?.errorCode || null;
};

export const formatCriticalReadingErrorMessage = (error) => {
  const body = getCriticalReadingErrorBody(error);
  const analysis = body?.analysis && typeof body.analysis === 'object' ? body.analysis : {};
  const errorCode = getCriticalReadingErrorCode(error);
  const message = body?.message || analysis?.message || error?.message;
  if (errorCode === 'paper_not_indexed' || errorCode === 'rag_index_unavailable') {
    return message || '当前论文尚未完成全文索引，请重新上传或重新解析后再试。';
  }
  if (error?.message === 'Network Error' || error?.code === 'ERR_NETWORK') {
    return '无法连接后端服务。请确认 Docker Desktop 已启动，并且 Java 网关 http://localhost:8081/api 正在运行。';
  }
  return message || '批判性阅读失败，请稍后重试。';
};
