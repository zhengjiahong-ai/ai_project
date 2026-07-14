import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart3,
  BookOpen,
  Bookmark,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  Info,
  LayoutDashboard,
  MessageSquare,
  Network,
  Search,
  Sparkles,
} from 'lucide-react';
import { Group, Panel, Separator } from 'react-resizable-panels';

import BackgroundKnowledgePanel from './components/BackgroundKnowledgePanel.jsx';
import BackgroundReaderProfileEditor from './components/BackgroundReaderProfileEditor.jsx';
import AgentWorkspace from './components/agent/AgentWorkspace.jsx';
import BottomWorkbench from './components/BottomWorkbench.jsx';
import {
  createDefaultReaderProfile,
  summarizeReaderProfile,
} from './components/backgroundKnowledgePanelModel.js';
import ChatPanel from './components/ChatPanel';
import CriticalAnalysisPanel from './components/CriticalAnalysisPanel';
import CodeExecutionApprovalCenter from './components/CodeExecutionApprovalCenter.jsx';
import DeepResearchPanel from './components/DeepResearchPanel.jsx';
import LibrarySidebar from './components/LibrarySidebar';
import Navbar from './components/Navbar';
import PaperAnalysis from './components/PaperAnalysis';
import PdfViewer from './components/PdfViewer';
import SocraticQuestionsPanel from './components/SocraticQuestionsPanel';
import TranslationPanel from './components/TranslationPanel';
import PaperWriterPanel from './components/PaperWriterPanel.jsx';
import { useAbortableChat } from './hooks/useAbortableChat.js';
import { usePaperArtifacts } from './hooks/usePaperArtifacts.js';
import { usePaperSession } from './hooks/usePaperSession.js';
import { useReadingWorkspace } from './hooks/useReadingWorkspace.js';
import { useTaskActivity } from './hooks/useTaskActivity.js';
import { useThemePreference } from './hooks/useThemePreference.js';
import { deletePaperScopedRecords, initDB } from './services/localDb.js';
import {
  clearStoredLastPdfId,
  persistLibraryReadingProgress,
  persistMessages,
  persistNotes,
  persistWorkbenchCards,
  persistSocraticSession,
  persistStoredActiveTab,
  persistStoredLastPdfId,
  persistTranslationState,
  persistUploadedPaperSession,
} from './services/workspaceSession.js';
import { apiService } from './services/api';
import {
  planPageTranslationState,
  preparePageTranslationRequest,
  shouldPreferPlainPageTranslation,
} from './utils/pageTranslationRequest.js';
import {
  createEmptyTranslationState,
  normalizeTranslationPage,
  normalizeTranslationState,
} from './utils/translationState.js';
import {
  SOCRATIC_TOTAL_QUESTIONS,
  createEmptySocraticSession,
  normalizeSocraticSession,
} from './utils/socraticSessionModel.js';
import {
  buildStudyProgressSnapshot,
  calculateReadingProgress,
} from './utils/studyProgress.js';
import {
  TERMINAL_RESEARCH_STATUSES,
  createEmptyDeepResearchState,
  normalizeResearchBriefPreview,
  normalizeTraceSummary,
  normalizeResearchTask,
  shouldRestoreLatestResearchTask,
} from './components/deepResearchPanelModel.js';
import {
  buildReadingWorkflowSuggestions,
  getPrimaryReadingWorkflowSuggestion,
} from './components/readingWorkflowModel.js';
import appVersionRaw from '../VERSION?raw';

const workflowStages = [
  {
    id: 'reading',
    label: '浅读解构',
    shortLabel: '阶段一',
    description: '先理清论文框架，再消除局部阅读障碍。',
    tabIds: ['deconstruct', 'chat', 'translation'],
  },
  {
    id: 'analysis',
    label: '深度探究',
    shortLabel: '阶段二',
    description: '围绕背景、批判与深挖建立完整理解。',
    tabIds: ['background', 'socratic', 'analysis', 'deep-research'],
  },
  {
    id: 'assets',
    label: '知识内化',
    shortLabel: '阶段三',
    description: '把洞察、证据和笔记整理成长期资产。',
    tabIds: ['notes'],
  },
];

const APP_VERSION = appVersionRaw.trim() || '0.0.0';
const DEFAULT_MODEL_NAME = 'DeepSeek V4';

const WELCOME_MESSAGE = {
  role: 'ai',
  content: '您好，我是您的 AI 学术助手。上传论文后，您可以直接选中文本进行提问、批判性阅读，并保留对话记录。',
};

const workspaceTabs = [
  { id: 'chat', label: '问答', icon: MessageSquare },
  { id: 'deconstruct', label: '篇章解构', icon: LayoutDashboard },
  { id: 'analysis', label: '批判阅读', icon: BarChart3 },
  { id: 'translation', label: '逐页翻译', icon: BookOpen },
  { id: 'background', label: '背景补课', icon: Network },
  { id: 'socratic', label: '引导学习', icon: Sparkles },
  { id: 'deep-research', label: '深度研究', icon: Search },
  { id: 'paper-writer', label: '论文写作', icon: FileText },
  { id: 'notes', label: '笔记', icon: Bookmark },
];

const workspaceTabSections = [
  {
    id: 'reading',
    label: '阅读助手',
    description: '围绕当前页面的即时理解与辅助阅读。',
    tabIds: ['chat', 'deconstruct', 'translation'],
  },
  {
    id: 'analysis',
    label: '分析研究',
    description: '偏重批判、补课、引导学习与研究推进。',
    tabIds: ['analysis', 'background', 'socratic', 'deep-research', 'paper-writer'],
  },
  {
    id: 'assets',
    label: '资产沉淀',
    description: '查看当前论文的长期沉淀与工作台入口。',
    tabIds: ['notes'],
  },
];

const DEFAULT_ACTIVE_TAB = 'chat';
const WORKBENCH_EXPANDED_SIZE = 32;
const WORKBENCH_COLLAPSED_SIZE = 18;
const WORKBENCH_COLLAPSE_THRESHOLD = 22;
const THEME_STORAGE_KEY = 'pixiu-theme';
const DEFAULT_BACKGROUND_READER_PROFILE = createDefaultReaderProfile();
const RESEARCH_POLL_INTERVAL_MS = 1500;
const STRUCTURED_TRANSLATION_TIMEOUT_MS = 90000;

const normalizeBackgroundKnowledgeLevel = (value) => {
  const text = `${value ?? ''}`.trim().toLowerCase();
  if (['入门', 'beginner', 'novice', '基础'].includes(text)) {
    return '入门';
  }
  if (['进阶', 'advanced', 'expert', '深入'].includes(text)) {
    return '进阶';
  }
  return '一般';
};

const normalizeReaderTagList = (value) => {
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

const normalizeBackgroundReaderProfile = (value) => {
  const profile = value && typeof value === 'object' ? value : {};
  const preferredDepthText = `${profile.preferredDepth ?? ''}`.trim();
  return {
    selfAssessedFamiliarity: normalizeBackgroundKnowledgeLevel(
      profile.selfAssessedFamiliarity || profile.user_knowledge_level || DEFAULT_BACKGROUND_READER_PROFILE.selfAssessedFamiliarity,
    ),
    preferredDepth: ['速览', '标准', '深入'].includes(preferredDepthText)
      ? preferredDepthText
      : preferredDepthText === '快速' || preferredDepthText === '简要'
        ? '速览'
        : preferredDepthText === '深度'
          ? '深入'
          : DEFAULT_BACKGROUND_READER_PROFILE.preferredDepth,
    learningGoal: `${profile.learningGoal ?? ''}`.trim(),
    knownConcepts: normalizeReaderTagList(profile.knownConcepts),
    confusingConcepts: normalizeReaderTagList(profile.confusingConcepts),
  };
};

const getWorkspaceSectionId = (tabId) =>
  workspaceTabSections.find((section) => section.tabIds.includes(tabId))?.id || workspaceTabSections[0].id;

const getWorkflowStageId = (tabId) =>
  workflowStages.find((stage) => stage.tabIds.includes(tabId))?.id || workflowStages[0].id;

const clampSnippet = (text, maxLength = 96) => {
  const normalized = `${text || ''}`.replace(/\s+/g, ' ').trim();
  if (!normalized) {
    return '';
  }

  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized;
};

const sectionDisplayNames = {
  abstract: '摘要',
  introduction: '1 Introduction',
  methods: '3 Methodology',
  results: '4 Experiments',
  discussion: '5 Discussion',
  conclusion: '6 Conclusion',
};

const outlineSourceLabels = {
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

const coerceFiniteNumber = (value) => {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

const getOutlineLevel = (label) => {
  const text = `${label || ''}`.trim();
  const numberMatch = text.match(/^\s*(?:section\s+)?(\d+(?:\.\d+)*)(?:[.)])?\s*/i);

  if (!numberMatch) {
    return 1;
  }

  return Math.min(4, Math.max(1, numberMatch[1].split('.').filter(Boolean).length));
};

const getOutlinePageLabel = (page, pageIndex) => {
  if (Number.isFinite(page) && page > 0) {
    return `p.${page}`;
  }

  if (Number.isFinite(pageIndex)) {
    return `p.${pageIndex + 1}`;
  }

  return '';
};

const normalizeOutlinePage = (section) => {
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

const flattenOutlineHierarchy = (rawItems) => {
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

const buildPaperOutlineModel = (deconstructData) => {
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

const getVisibleOutlineItems = (items, collapsedIds, query) => {
  const normalizedQuery = `${query || ''}`.trim().toLowerCase();

  if (!normalizedQuery) {
    return items.filter((item) => !item.ancestorIds.some((ancestorId) => collapsedIds[ancestorId]));
  }

  const visibleIds = new Set();
  items.forEach((item) => {
    const searchableText = [
      item.label,
      item.rawTitle,
      item.headingNumber,
      item.meta,
      item.pageLabel,
      item.preview,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();

    if (searchableText.includes(normalizedQuery)) {
      visibleIds.add(item.id);
      item.ancestorIds.forEach((ancestorId) => visibleIds.add(ancestorId));
    }
  });

  return items.filter((item) => visibleIds.has(item.id));
};

const resolveCurrentOutlineItem = (items, currentPageIndex) => {
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

const renderHighlightedText = (text, query) => {
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
      <mark key={`${matchIndex}-${matchedText}`} className="outline-search-mark">
        {matchedText}
      </mark>,
    );
    cursor = matchIndex + normalizedQuery.length;
    matchIndex = lowerText.indexOf(lowerQuery, cursor);
  }

  if (cursor < rawText.length) {
    parts.push(rawText.slice(cursor));
  }

  return parts;
};

const normalizeAuthors = (authors) => {
  if (Array.isArray(authors)) {
    return authors.filter(Boolean).join(', ');
  }

  return `${authors || ''}`.trim();
};

const formatUploadErrorMessage = (error) => {
  const responseMessage = error?.response?.data?.message || error?.response?.data?.detail;
  if (responseMessage) {
    return responseMessage;
  }

  if (error?.message === 'Network Error' || error?.code === 'ERR_NETWORK') {
    return '无法连接后端服务。请确认 Docker Desktop 已启动，并且 Java 网关 http://localhost:8081/api 正在运行。';
  }

  return error?.message || '上传失败，请确认后端服务已启动。';
};

const getCriticalReadingErrorBody = (error) => {
  const responseBody = error?.response?.data;
  if (responseBody && typeof responseBody === 'object') {
    return responseBody;
  }
  const payload = error?.payload;
  if (payload && typeof payload === 'object') {
    return payload;
  }
  return {};
};

const getCriticalReadingErrorCode = (error) => {
  const body = getCriticalReadingErrorBody(error);
  const analysis = body?.analysis && typeof body.analysis === 'object' ? body.analysis : {};
  return error?.code || body?.errorCode || analysis?.errorCode || null;
};

const formatCriticalReadingErrorMessage = (error) => {
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

export default function App() {
  const { theme, toggleTheme: handleToggleTheme } = useThemePreference(THEME_STORAGE_KEY);
  const [appMode, setAppMode] = useState('reader');
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfFileName, setPdfFileName] = useState(null);
  const [pdfId, setPdfId] = useState(null);
  const [messages, setMessages] = useState([WELCOME_MESSAGE]);
  const [activeTab, setActiveTab] = useState('chat');
  const [activeWorkspaceSectionId, setActiveWorkspaceSectionId] = useState(() => getWorkspaceSectionId(DEFAULT_ACTIVE_TAB));
  const [analysisData, setAnalysisData] = useState(null);
  const [backgroundKnowledgeData, setBackgroundKnowledgeData] = useState(null);
  const [backgroundReaderProfile, setBackgroundReaderProfile] = useState(DEFAULT_BACKGROUND_READER_PROFILE);
  const backgroundReaderProfileSummary = useMemo(
    () => summarizeReaderProfile(backgroundReaderProfile),
    [backgroundReaderProfile],
  );
  const [isRestored, setIsRestored] = useState(false);
  const [isTranslated, setIsTranslated] = useState(false);
  const [deconstructData, setDeconstructData] = useState(null);
  const [socraticSession, setSocraticSession] = useState(createEmptySocraticSession());
  const [translationState, setTranslationState] = useState(createEmptyTranslationState());
  const [deepResearchStateByPdf, setDeepResearchStateByPdf] = useState({});
  const [papersList, setPapersList] = useState([]);
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [isWorkbenchCollapsed, setIsWorkbenchCollapsed] = useState(false);
  const [isWorkspaceNavExpanded, setIsWorkspaceNavExpanded] = useState(false);
  const [focusedSourceRequest, setFocusedSourceRequest] = useState({
    anchorId: null,
    token: 0,
  });
  const {
    notes,
    setNotes,
    addNote,
    pdfHighlights,
    setPdfHighlights,
    workbenchCards,
    setWorkbenchCards,
    captureArtifact,
    removeArtifact,
    toggleArtifactPinned,
    updateArtifact,
    resetArtifacts,
  } = usePaperArtifacts();
  const {
    outlineQuery,
    setOutlineQuery,
    collapsedOutlineIds,
    pdfPageState,
    setPdfPageState,
    targetPageIndex,
    setTargetPageIndex,
    targetPageJumpToken,
    resetOutlineState,
    resetPageNavigation,
    jumpToPage,
    toggleOutlineCollapse,
  } = useReadingWorkspace();
  const { taskActivity, setTaskActive } = useTaskActivity();
  const {
    startChatRequest,
    finishChatRequest,
    abortChatRequest,
    isChatLoading,
  } = useAbortableChat();
  const isAiReady = taskActivity.aiReady;
  const isDeconstructing = taskActivity.deconstructing;
  const isAnalyzing = taskActivity.analyzing;
  const isBackgroundKnowledgeLoading = taskActivity.backgroundKnowledgeLoading;
  const isSocraticLoading = taskActivity.socraticLoading;

  const translationRequestsRef = useRef({});
  const translationRequestSequenceRef = useRef(0);
  const latestTranslationTokensRef = useRef({});
  const translationStateRef = useRef(createEmptyTranslationState());
  const papersListRef = useRef([]);
  const currentPdfIdRef = useRef(null);
  const restoredResearchPdfIdsRef = useRef(new Set());
  const workspaceTabsRef = useRef(null);
  const workbenchPanelRef = useRef(null);
  const currentPageTextRef = useRef({
    pageIndex: 0,
    pageText: '',
    pageLayout: null,
  });
  const lastNonTranslationTabRef = useRef(DEFAULT_ACTIVE_TAB);

  useEffect(() => {
    papersListRef.current = papersList;
  }, [papersList]);

  useEffect(() => {
    currentPdfIdRef.current = pdfId;
  }, [pdfId]);

  useEffect(() => {
    setActiveWorkspaceSectionId(getWorkspaceSectionId(activeTab));
  }, [activeTab]);

  useEffect(() => {
    resetOutlineState();
  }, [pdfId, resetOutlineState]);

  useEffect(() => {
    const activeTabButton = workspaceTabsRef.current?.querySelector('[data-active-tab="true"]');
    activeTabButton?.scrollIntoView({
      block: 'nearest',
      inline: 'nearest',
      behavior: 'smooth',
    });
  }, [activeTab]);

  useEffect(() => {
    translationStateRef.current = translationState;
  }, [translationState]);

  useEffect(() => {
    Object.values(translationRequestsRef.current).forEach((entry) => entry?.controller?.abort());
    translationRequestsRef.current = {};
    latestTranslationTokensRef.current = {};
  }, [pdfId]);

  useEffect(() => {
    if (activeTab !== 'translation') {
      lastNonTranslationTabRef.current = activeTab;
    }
  }, [activeTab]);

  const commitTranslationState = useCallback((nextStateOrUpdater) => {
    if (typeof nextStateOrUpdater === 'function') {
      setTranslationState((previousState) => {
        const nextState = nextStateOrUpdater(previousState);
        translationStateRef.current = nextState;
        return nextState;
      });
      return;
    }

    translationStateRef.current = nextStateOrUpdater;
    setTranslationState(nextStateOrUpdater);
  }, []);

  const setDeepResearchStateForPdf = useCallback((targetPdfId, nextStateOrUpdater) => {
    if (!targetPdfId) {
      return;
    }

    setDeepResearchStateByPdf((previousState) => {
      const previousResearchState = previousState[targetPdfId] || createEmptyDeepResearchState();
      const nextResearchState =
        typeof nextStateOrUpdater === 'function'
          ? nextStateOrUpdater(previousResearchState)
          : nextStateOrUpdater;

      return {
        ...previousState,
        [targetPdfId]: nextResearchState,
      };
    });
  }, []);

  const fetchDeepResearchTrace = useCallback(async (targetPdfId, traceId) => {
    const normalizedTraceId = `${traceId || ''}`.trim();
    if (!targetPdfId || !normalizedTraceId) {
      return null;
    }

    setDeepResearchStateForPdf(targetPdfId, (prev) => ({
      ...prev,
      isTraceLoading: true,
      traceError: '',
    }));

    try {
      const response = await apiService.getTrace(normalizedTraceId);
      const nextTraceSummary = normalizeTraceSummary(response?.trace);
      if (response?.status !== 'success' || !nextTraceSummary) {
        throw new Error(response?.message || 'Trace 查询失败');
      }

      setDeepResearchStateForPdf(targetPdfId, (prev) => {
        if ((prev.task?.traceId || '') !== normalizedTraceId) {
          return prev;
        }

        return {
          ...prev,
          traceSummary: nextTraceSummary,
          traceError: '',
          isTraceLoading: false,
        };
      });
      return nextTraceSummary;
    } catch (error) {
      console.error('Failed to fetch deep research trace.', error);
      setDeepResearchStateForPdf(targetPdfId, (prev) => {
        if ((prev.task?.traceId || '') !== normalizedTraceId) {
          return prev;
        }

        return {
          ...prev,
          traceError: error?.response?.data?.message || error?.message || 'Trace 查询失败。',
          isTraceLoading: false,
        };
      });
      return null;
    }
  }, [setDeepResearchStateForPdf]);

  const {
    restorePaperState,
    restoreLocalSession,
    restoreSelectedPaper,
    createReadyMessages,
  } = usePaperSession({
    apiService,
    welcomeMessage: WELCOME_MESSAGE,
    defaultActiveTab: DEFAULT_ACTIVE_TAB,
    normalizeBackgroundKnowledgeLevel,
    normalizeBackgroundReaderProfile,
    normalizeSocraticSession,
    normalizeTranslationState,
    setPdfId,
    setPdfFile,
    setPdfFileName,
    setDeconstructData,
    setNotes,
    setAnalysisData,
    setBackgroundKnowledgeData,
    setBackgroundReaderProfile,
    setMessages,
    setPdfHighlights,
    setWorkbenchCards,
    setSocraticSession,
    commitTranslationState,
    setIsTranslated,
    currentPageTextRef,
    setPdfPageState,
    jumpToPage,
    setTargetPageIndex,
    setActiveTab,
    lastNonTranslationTabRef,
    setPapersList,
    setIsRestored,
    setTaskActive,
    papersListRef,
  });

  const handlePdfUpload = useCallback(async (file) => {
    if (!file) return;

    setPdfFileName(file.name);
    setPdfFile(URL.createObjectURL(file));
    setTaskActive('aiReady', false);
    setTaskActive('deconstructing', true);

    try {
      const response = await apiService.uploadPdf(file);
      if (!response || response.status !== 'success') {
        throw new Error(response?.message || '论文上传失败');
      }

      const readyMessages = createReadyMessages(file.name);
      const initialStudyProgress = buildStudyProgressSnapshot({
        pdfId: response.pdfId,
        pdfPageState: { pageIndex: 0, totalPages: 0 },
        deconstructData: response,
        analysisData: null,
        backgroundKnowledgeData: null,
        socraticSession: createEmptySocraticSession(response.pdfId),
        translationState: createEmptyTranslationState(response.pdfId),
        messages: readyMessages,
        notes: [],
        pdfHighlights: [],
        workbenchCards: [],
        deepResearchState: createEmptyDeepResearchState(),
      });
      const newEntry = {
        id: response.pdfId,
        title: response.title || file.name,
        filename: file.name,
        authors: normalizeAuthors(response.authors),
        parseStatus: response.parseStatus || (response.ragIndexed === false ? '索引异常' : '已解析'),
        parseMessage: response.parseMessage || null,
        ragIndexed: response.ragIndexed !== false,
        ragChunkCount: response.ragChunkCount || 0,
        ragErrorCode: response.ragErrorCode || null,
        indexMessage: response.message || null,
        sectionCount: response.paper_structure?.sections?.length || 0,
        readingProgress: initialStudyProgress.readingProgress,
        currentPage: initialStudyProgress.currentPage,
        totalPages: initialStudyProgress.totalPages,
        studyProgress: initialStudyProgress.studyProgress,
        studyPhase: initialStudyProgress.studyPhase,
        studySummary: initialStudyProgress.studySummary,
        progressSignals: initialStudyProgress.progressSignals,
        timestamp: Date.now(),
        updatedAt: Date.now(),
      };

      const db = await initDB();
      await persistUploadedPaperSession({
        db,
        file,
        pdfId: response.pdfId,
        response,
        readyMessages,
        libraryEntry: newEntry,
      });

      setPdfId(response.pdfId);
      setDeconstructData(response);
      setAnalysisData(null);
      setBackgroundKnowledgeData(null);
      setBackgroundReaderProfile(DEFAULT_BACKGROUND_READER_PROFILE);
      resetArtifacts();
      setMessages(readyMessages);
      setSocraticSession(createEmptySocraticSession(response.pdfId));
      commitTranslationState(createEmptyTranslationState(response.pdfId));
      setIsTranslated(false);
      currentPageTextRef.current = { pageIndex: 0, pageText: '', pageLayout: null };
      resetPageNavigation();
      setActiveTab('deconstruct');
      setPapersList((prev) => [newEntry, ...prev.filter((paper) => paper.id !== response.pdfId)]);
      persistStoredLastPdfId(response.pdfId);

      if (response?.ragIndexed === false && response?.message) {
        window.alert(response.message);
      }
    } catch (error) {
      console.error('Failed to upload PDF.', error);
      setPdfFile(null);
      setPdfFileName(null);
      setPdfId(null);
      setSocraticSession(createEmptySocraticSession());
      setBackgroundKnowledgeData(null);
      setBackgroundReaderProfile(DEFAULT_BACKGROUND_READER_PROFILE);
      commitTranslationState(createEmptyTranslationState());
      setIsTranslated(false);
      currentPageTextRef.current = { pageIndex: 0, pageText: '', pageLayout: null };
      resetArtifacts();
      resetPageNavigation();
      const uploadErrorMessage = formatUploadErrorMessage(error);
      window.setTimeout(() => {
        window.alert(uploadErrorMessage);
      }, 0);
    } finally {
      setTaskActive('aiReady', true);
      setTaskActive('deconstructing', false);
    }
  }, [commitTranslationState, createReadyMessages, resetArtifacts, resetPageNavigation, setTaskActive]);



  useEffect(() => {
    restoreLocalSession();
  }, [restoreLocalSession]);

  const handleSelectPaper = restoreSelectedPaper;

  const handleWorkspaceTabsWheel = useCallback((event) => {
    const tabsElement = event.currentTarget;
    const maxScrollLeft = tabsElement.scrollWidth - tabsElement.clientWidth;

    if (maxScrollLeft <= 0) {
      return;
    }

    const delta =
      Math.abs(event.deltaX) > Math.abs(event.deltaY)
        ? event.deltaX
        : event.deltaY;

    if (!delta) {
      return;
    }

    const nextScrollLeft = Math.max(0, Math.min(maxScrollLeft, tabsElement.scrollLeft + delta));
    if (nextScrollLeft === tabsElement.scrollLeft) {
      return;
    }

    event.preventDefault();
    tabsElement.scrollLeft = nextScrollLeft;
  }, []);

  const handleToggleWorkbenchCollapsed = useCallback(() => {
    if (isWorkbenchCollapsed) {
      workbenchPanelRef.current?.resize(WORKBENCH_EXPANDED_SIZE);
      setIsWorkbenchCollapsed(false);
      return;
    }

    workbenchPanelRef.current?.resize(WORKBENCH_COLLAPSED_SIZE);
    setIsWorkbenchCollapsed(true);
  }, [isWorkbenchCollapsed]);

  const handleSelectOutlineItem = useCallback((item) => {
    setActiveTab('deconstruct');
    if (Number.isFinite(item.pageIndex)) {
      jumpToPage(item.pageIndex);
    }
  }, [jumpToPage]);

  const handleDeletePaper = useCallback(async (targetPdfId) => {
    if (!window.confirm('确定移除这篇论文及其所有关联聊天、笔记和引导学习记录吗？')) return;

    try {
      const db = await initDB();
      await Promise.all([
        deletePaperScopedRecords(db, targetPdfId),
        db.delete('libraryStore', targetPdfId),
      ]);

      setPapersList((prev) => prev.filter((paper) => paper.id !== targetPdfId));
      setDeepResearchStateByPdf((prev) => {
        if (!Object.prototype.hasOwnProperty.call(prev, targetPdfId)) {
          return prev;
        }
        const nextState = { ...prev };
        delete nextState[targetPdfId];
        return nextState;
      });

      if (pdfId === targetPdfId) {
        setPdfId(null);
        setPdfFile(null);
        setPdfFileName(null);
        setMessages([WELCOME_MESSAGE]);
        resetArtifacts();
        setDeconstructData(null);
        setAnalysisData(null);
        setBackgroundKnowledgeData(null);
        setBackgroundReaderProfile(DEFAULT_BACKGROUND_READER_PROFILE);
        setSocraticSession(createEmptySocraticSession());
        commitTranslationState(createEmptyTranslationState());
        setIsTranslated(false);
        currentPageTextRef.current = { pageIndex: 0, pageText: '', pageLayout: null };
        resetPageNavigation();
        setActiveTab(DEFAULT_ACTIVE_TAB);
        clearStoredLastPdfId();
      }
    } catch (error) {
      console.error('Failed to delete paper.', error);
    }
  }, [commitTranslationState, pdfId, resetArtifacts, resetPageNavigation]);

  useEffect(() => {
    if (!isRestored || !pdfId) return;

    const saveMessages = async () => {
      try {
        const db = await initDB();
        await persistMessages(db, pdfId, messages);
        persistStoredActiveTab(
          activeTab === 'translation' ? lastNonTranslationTabRef.current || DEFAULT_ACTIVE_TAB : activeTab,
        );
      } catch (error) {
        console.error('Failed to persist messages.', error);
      }
    };

    saveMessages();
  }, [activeTab, isRestored, messages, pdfId]);

  useEffect(() => {
    if (!isRestored || !pdfId) return;

    const saveNotes = async () => {
      try {
        const db = await initDB();
        await persistNotes(db, pdfId, notes);
      } catch (error) {
        console.error('Failed to persist notes.', error);
      }
    };

    saveNotes();
  }, [isRestored, notes, pdfId]);

  useEffect(() => {
    if (!isRestored || !pdfId) return;

    const saveWorkbenchCards = async () => {
      try {
        const db = await initDB();
        await persistWorkbenchCards(db, pdfId, workbenchCards);
      } catch (error) {
        console.error('Failed to persist workbench cards.', error);
      }
    };

    saveWorkbenchCards();
  }, [isRestored, pdfId, workbenchCards]);

  useEffect(() => {
    if (!isRestored || !pdfId || socraticSession?.pdfId !== pdfId) return;

    const saveSocraticSession = async () => {
      try {
        const db = await initDB();
        await persistSocraticSession(db, pdfId, socraticSession);
      } catch (error) {
        console.error('Failed to persist Socratic session.', error);
      }
    };

    saveSocraticSession();
  }, [isRestored, pdfId, socraticSession]);

  useEffect(() => {
    if (!isRestored || !pdfId || translationState?.pdfId !== pdfId) return;

    const saveTranslationState = async () => {
      try {
        const db = await initDB();
        await persistTranslationState(db, pdfId, translationState);
      } catch (error) {
        console.error('Failed to persist translation state.', error);
      }
    };

    saveTranslationState();
  }, [isRestored, pdfId, translationState]);

  const currentStudyProgressSnapshot = useMemo(
    () =>
      buildStudyProgressSnapshot({
        pdfId,
        pdfPageState,
        deconstructData,
        analysisData,
        backgroundKnowledgeData,
        socraticSession,
        translationState,
        messages,
        notes,
        pdfHighlights,
        workbenchCards,
        deepResearchState: pdfId ? deepResearchStateByPdf[pdfId] || createEmptyDeepResearchState() : null,
      }),
    [
      analysisData,
      backgroundKnowledgeData,
      deepResearchStateByPdf,
      deconstructData,
      messages,
      notes,
      pdfHighlights,
      pdfId,
      pdfPageState,
      socraticSession,
      translationState,
      workbenchCards,
    ],
  );

  useEffect(() => {
    if (!isRestored || !pdfId) return;

    const {
      readingProgress: nextProgress,
      currentPage: nextCurrentPage,
      totalPages: nextTotalPages,
      studyProgress,
      studyPhase,
      studySummary,
      progressSignals,
    } = currentStudyProgressSnapshot;
    const updatedAt = Date.now();

    setPapersList((prev) => {
      let didUpdate = false;
      const nextList = prev.map((paper) => {
        if (paper.id !== pdfId) return paper;

        if (
          paper.readingProgress === nextProgress &&
          paper.currentPage === nextCurrentPage &&
          paper.totalPages === nextTotalPages &&
          paper.studyProgress === studyProgress &&
          paper.studyPhase === studyPhase &&
          paper.studySummary === studySummary &&
          JSON.stringify(paper.progressSignals || {}) === JSON.stringify(progressSignals || {})
        ) {
          return paper;
        }

        didUpdate = true;
        return {
          ...paper,
          readingProgress: nextProgress,
          currentPage: nextCurrentPage,
          totalPages: nextTotalPages,
          studyProgress,
          studyPhase,
          studySummary,
          progressSignals,
          updatedAt,
        };
      });

      return didUpdate ? nextList : prev;
    });

    const saveLibraryProgress = async () => {
      try {
        const db = await initDB();
        const currentPaper = await db.get('libraryStore', pdfId);
        if (
          currentPaper &&
          currentPaper.readingProgress === nextProgress &&
          currentPaper.currentPage === nextCurrentPage &&
          currentPaper.totalPages === nextTotalPages &&
          currentPaper.studyProgress === studyProgress &&
          currentPaper.studyPhase === studyPhase &&
          currentPaper.studySummary === studySummary &&
          JSON.stringify(currentPaper.progressSignals || {}) === JSON.stringify(progressSignals || {})
        ) {
          return;
        }

        await persistLibraryReadingProgress(db, pdfId, {
          readingProgress: nextProgress,
          currentPage: nextCurrentPage,
          totalPages: nextTotalPages,
          studyProgress,
          studyPhase,
          studySummary,
          progressSignals,
          updatedAt,
        });
      } catch (error) {
        console.error('Failed to persist library reading progress.', error);
      }
    };

    saveLibraryProgress();
  }, [currentStudyProgressSnapshot, isRestored, pdfId]);

  const handleStartAnalysis = useCallback(async () => {
    if (!pdfId) {
      window.alert('请先上传 PDF 文件。');
      return;
    }

    setActiveTab('analysis');
    setTaskActive('analyzing', true);

    try {
      const response = await apiService.criticalReading(pdfId);
      const payload = response?.analysis ?? response;
      const isSuccess = response?.status === 'success' || payload?.status === 'success';
      if (!isSuccess) {
        const analysisError = new Error(response?.message || payload?.message || '批判性阅读失败');
        analysisError.code = response?.errorCode || payload?.errorCode || null;
        analysisError.payload = response || payload || null;
        throw analysisError;
      }

      setAnalysisData(payload);
      const db = await initDB();
      await db.put('analysisStore', payload, pdfId);
    } catch (error) {
      console.error('Failed to run critical reading.', error);
      const errorCode = getCriticalReadingErrorCode(error);
      const errorMessage = formatCriticalReadingErrorMessage(error);
      if (errorCode === 'paper_not_indexed' || errorCode === 'rag_index_unavailable') {
        try {
          const db = await initDB();
          const paper = await db.get('libraryStore', pdfId);
          if (paper) {
            const updatedPaper = {
              ...paper,
              parseStatus: '索引异常',
              ragIndexed: false,
              ragErrorCode: errorCode,
              indexMessage: errorMessage,
              updatedAt: Date.now(),
            };
            await db.put('libraryStore', updatedPaper);
            setPapersList((prev) => prev.map((item) => (item.id === pdfId ? updatedPaper : item)));
          }
        } catch (storeError) {
          console.error('Failed to mark paper index status.', storeError);
        }
      }
      window.alert(errorMessage);
    } finally {
      setTaskActive('analyzing', false);
    }
  }, [pdfId, setTaskActive]);

  const handleGenerateBackgroundKnowledge = useCallback(async (selectedProfile = backgroundReaderProfile) => {
    if (!pdfId) {
      window.alert('请先上传 PDF 文件。');
      return;
    }

    setActiveTab('background');
    setTaskActive('backgroundKnowledgeLoading', true);

    try {
      const requestedProfile = normalizeBackgroundReaderProfile(selectedProfile);
      const requestedKnowledgeLevel = normalizeBackgroundKnowledgeLevel(requestedProfile.selfAssessedFamiliarity);
      const researchProblem = deconstructData?.paper_structure?.research_problem;
      const coreHypothesis = deconstructData?.paper_structure?.core_hypothesis;
      const paperTopic =
        typeof researchProblem === 'string' && researchProblem.trim()
          ? researchProblem
          : typeof coreHypothesis === 'string' && coreHypothesis.trim()
            ? coreHypothesis
            : null;
      const recentQuestions = messages
        .filter((message) => message?.role === 'user')
        .map((message) => `${message?.content ?? ''}`.trim())
        .filter(Boolean)
        .slice(-4);
      const behaviorSignals = {
        questionCount: recentQuestions.length,
        highlightCount: pdfHighlights.length,
        noteCount: notes.length,
        artifactCount: workbenchCards.length,
        translationUsageCount: translationState?.pages ? Object.keys(translationState.pages).length : 0,
        recentQuestions,
        currentPage: Number.isFinite(pdfPageState?.pageIndex) ? pdfPageState.pageIndex + 1 : null,
        currentSection: `${deconstructData?.paper_structure?.title || ''}`.trim() || null,
        activeWorkspaceTab: activeTab,
      };

      const response = await apiService.backgroundKnowledge({
        pdfId,
        paperSkeleton: deconstructData?.paper_skeleton || null,
        paperStructure: deconstructData?.paper_structure || null,
        paper_topic: paperTopic,
        user_knowledge_level: requestedKnowledgeLevel,
        reader_profile: requestedProfile,
        behavior_signals: behaviorSignals,
      });

      if (!response || response.status !== 'success') {
        throw new Error(response?.message || '背景知识图谱生成失败');
      }

      setBackgroundKnowledgeData(response);
      setBackgroundReaderProfile(normalizeBackgroundReaderProfile(
        response?.reader_profile || {
          ...requestedProfile,
          selfAssessedFamiliarity: response?.user_knowledge_level || requestedKnowledgeLevel,
        },
      ));
      const db = await initDB();
      await db.put('backgroundKnowledgeStore', response, pdfId);
    } catch (error) {
      console.error('Failed to generate background knowledge graph.', error);
      window.alert(error?.response?.data?.message || error?.message || '背景知识图谱生成失败，请稍后重试。');
    } finally {
      setTaskActive('backgroundKnowledgeLoading', false);
    }
  }, [
    activeTab,
    backgroundReaderProfile,
    deconstructData,
    messages,
    notes.length,
    pdfHighlights.length,
    pdfId,
    pdfPageState?.pageIndex,
    setTaskActive,
    translationState?.pages,
    workbenchCards.length,
  ]);

  const handleDeepResearchQuestionChange = useCallback((nextQuestionDraft) => {
    if (!pdfId) {
      return;
    }

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      questionDraft: nextQuestionDraft,
      errorMessage: '',
      briefPreview: null,
      briefError: '',
    }));
  }, [pdfId, setDeepResearchStateForPdf]);

  const handleDeepResearchBriefConstraintsChange = useCallback((nextConstraintsDraft) => {
    if (!pdfId) {
      return;
    }

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      briefConstraintsDraft: nextConstraintsDraft,
      briefError: '',
    }));
  }, [pdfId, setDeepResearchStateForPdf]);

  const handlePreviewResearchBrief = useCallback(async () => {
    if (!pdfId) {
      return;
    }

    const currentState = deepResearchStateByPdf[pdfId] || createEmptyDeepResearchState();
    const question = `${currentState.questionDraft || ''}`.trim();
    if (!question) {
      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        briefError: '请输入研究问题后再生成研究 brief。',
      }));
      return;
    }

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      isPreviewingBrief: true,
      briefError: '',
      errorMessage: '',
    }));

    try {
      const response = await apiService.previewResearchBrief(
        question,
        pdfId,
        deconstructData?.paper_skeleton || null,
        currentState.briefConstraintsDraft || '',
      );
      const nextPreview = normalizeResearchBriefPreview(response?.briefPreview);
      if (response?.status !== 'success' || !nextPreview) {
        throw new Error(response?.message || '研究 brief 生成失败');
      }

      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        questionDraft: question,
        briefPreview: nextPreview,
        briefError: '',
        isPreviewingBrief: false,
      }));
    } catch (error) {
      console.error('Failed to preview deep research brief.', error);
      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        isPreviewingBrief: false,
        briefError: error?.response?.data?.message || error?.message || '研究 brief 生成失败，请稍后重试。',
      }));
    }
  }, [deepResearchStateByPdf, deconstructData, pdfId, setDeepResearchStateForPdf]);

  const handleStartResearchTask = useCallback(async ({ useBriefPreview = false } = {}) => {
    if (!pdfId) {
      return;
    }

    const currentState = deepResearchStateByPdf[pdfId] || createEmptyDeepResearchState();
    const question = `${currentState.questionDraft || ''}`.trim();
    if (!question) {
      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        errorMessage: '请输入研究问题后再启动深度研究任务。',
      }));
      return;
    }

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      isCreating: true,
      isCancelling: false,
      errorMessage: '',
      pollError: '',
      briefError: '',
    }));

    try {
      const response = await apiService.createResearchTask(
        question,
        pdfId,
        deconstructData?.paper_skeleton || null,
        useBriefPreview ? currentState.briefConstraintsDraft || '' : '',
        useBriefPreview ? currentState.briefPreview : null,
        Boolean(currentState.allowExternalSearch),
      );
      const nextTask = normalizeResearchTask(response?.task);
      if (response?.status !== 'success' || !nextTask) {
        throw new Error(response?.message || '深度研究任务创建失败');
      }

      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        questionDraft: question,
        task: nextTask,
        errorMessage: '',
        pollError: '',
        isCreating: false,
        isCancelling: false,
        traceSummary: null,
        traceError: '',
        isTraceLoading: false,
      }));

      fetchDeepResearchTrace(pdfId, nextTask.traceId);

      if (currentPdfIdRef.current === pdfId) {
        setActiveTab('deep-research');
      }
    } catch (error) {
      console.error('Failed to create deep research task.', error);
      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        isCreating: false,
        errorMessage: error?.response?.data?.message || error?.message || '深度研究任务创建失败，请稍后重试。',
      }));
    }
  }, [deepResearchStateByPdf, deconstructData, fetchDeepResearchTrace, pdfId, setDeepResearchStateForPdf]);

  const handleRefreshResearchTask = useCallback(async () => {
    if (!pdfId) {
      return;
    }

    const currentTaskId = deepResearchStateByPdf[pdfId]?.task?.taskId;
    if (!currentTaskId) {
      return;
    }

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      errorMessage: '',
      pollError: '',
    }));

    try {
      const response = await apiService.getResearchTask(currentTaskId);
      const nextTask = normalizeResearchTask(response?.task);
      if (response?.status !== 'success' || !nextTask) {
        throw new Error(response?.message || '深度研究任务状态刷新失败');
      }

      setDeepResearchStateForPdf(pdfId, (prev) => {
        if ((prev.task?.taskId || '') !== currentTaskId) {
          return prev;
        }

        return {
          ...prev,
          task: nextTask,
          errorMessage: '',
          pollError: '',
          isCreating: false,
          isCancelling: false,
        };
      });

      fetchDeepResearchTrace(pdfId, nextTask.traceId);
    } catch (error) {
      console.error('Failed to refresh deep research task.', error);
      setDeepResearchStateForPdf(pdfId, (prev) => {
        if ((prev.task?.taskId || '') !== currentTaskId) {
          return prev;
        }

        return {
          ...prev,
          pollError: error?.response?.data?.message || error?.message || '深度研究任务状态刷新失败。',
        };
      });
    }
  }, [deepResearchStateByPdf, fetchDeepResearchTrace, pdfId, setDeepResearchStateForPdf]);

  const handleReviewResearchPlan = useCallback(async (payload) => {
    const taskId = deepResearchStateByPdf[pdfId]?.task?.taskId;
    if (!pdfId || !taskId) return;
    try {
      const response = await apiService.reviewResearchPlan(taskId, payload);
      const task = normalizeResearchTask(response?.task);
      if (!task) throw new Error(response?.message || '计划确认失败');
      setDeepResearchStateForPdf(pdfId, (prev) => ({ ...prev, task, errorMessage: '', pollError: '' }));
    } catch (error) {
      setDeepResearchStateForPdf(pdfId, (prev) => ({ ...prev, errorMessage: error?.response?.data?.message || error?.message || '计划确认失败。' }));
    }
  }, [deepResearchStateByPdf, pdfId, setDeepResearchStateForPdf]);

  const handleReviewResearchFinal = useCallback(async (payload) => {
    const taskId = deepResearchStateByPdf[pdfId]?.task?.taskId;
    if (!pdfId || !taskId) return;
    try {
      const response = await apiService.reviewResearchFinal(taskId, payload);
      const task = normalizeResearchTask(response?.task);
      if (!task) throw new Error(response?.message || '终稿确认失败');
      setDeepResearchStateForPdf(pdfId, (prev) => ({ ...prev, task, errorMessage: '', pollError: '' }));
      fetchDeepResearchTrace(pdfId, task.traceId);
    } catch (error) {
      setDeepResearchStateForPdf(pdfId, (prev) => ({ ...prev, errorMessage: error?.response?.data?.message || error?.message || '终稿确认失败。' }));
    }
  }, [deepResearchStateByPdf, fetchDeepResearchTrace, pdfId, setDeepResearchStateForPdf]);

  const handleCancelResearchTask = useCallback(async () => {
    if (!pdfId) {
      return;
    }

    const currentTaskId = deepResearchStateByPdf[pdfId]?.task?.taskId;
    if (!currentTaskId) {
      return;
    }

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      isCancelling: true,
      errorMessage: '',
      pollError: '',
    }));

    try {
      const response = await apiService.cancelResearchTask(currentTaskId);
      const nextTask = normalizeResearchTask(response?.task);
      if (response?.status !== 'success' || !nextTask) {
        throw new Error(response?.message || '深度研究任务取消失败');
      }

      setDeepResearchStateForPdf(pdfId, (prev) => {
        if ((prev.task?.taskId || '') !== currentTaskId) {
          return prev;
        }

        return {
          ...prev,
          task: nextTask,
          errorMessage: '',
          pollError: '',
          isCreating: false,
          isCancelling: false,
        };
      });

      fetchDeepResearchTrace(pdfId, nextTask.traceId);
    } catch (error) {
      console.error('Failed to cancel deep research task.', error);
      setDeepResearchStateForPdf(pdfId, (prev) => {
        if ((prev.task?.taskId || '') !== currentTaskId) {
          return prev;
        }

        return {
          ...prev,
          isCancelling: false,
          errorMessage: error?.response?.data?.message || error?.message || '深度研究任务取消失败。',
        };
      });
    }
  }, [deepResearchStateByPdf, fetchDeepResearchTrace, pdfId, setDeepResearchStateForPdf]);

  useEffect(() => {
    if (!pdfId) {
      return undefined;
    }

    const currentState = deepResearchStateByPdf[pdfId] || createEmptyDeepResearchState();
    if (
      restoredResearchPdfIdsRef.current.has(pdfId) ||
      !shouldRestoreLatestResearchTask(pdfId, currentState)
    ) {
      return undefined;
    }

    let isCancelled = false;
    const targetPdfId = pdfId;
    restoredResearchPdfIdsRef.current.add(targetPdfId);

    const restoreLatestTask = async () => {
      try {
        const response = await apiService.getLatestResearchTask(targetPdfId);
        const restoredTask = normalizeResearchTask(response?.task);
        if (isCancelled || response?.status !== 'success' || !restoredTask) {
          return;
        }

        setDeepResearchStateForPdf(targetPdfId, (prev) => {
          if (prev.task?.taskId) {
            return prev;
          }
          return {
            ...prev,
            task: restoredTask,
            questionDraft: restoredTask.question || prev.questionDraft || '',
            errorMessage: '',
            pollError: '',
            isCreating: false,
            isCancelling: false,
          };
        });

        fetchDeepResearchTrace(targetPdfId, restoredTask.traceId);
      } catch (error) {
        if (isCancelled || error?.response?.status === 404) {
          return;
        }

        setDeepResearchStateForPdf(targetPdfId, (prev) => {
          if (prev.task?.taskId) {
            return prev;
          }
          return {
            ...prev,
            pollError: error?.response?.data?.message || error?.message || '深度研究历史任务恢复失败。',
          };
        });
      }
    };

    restoreLatestTask();

    return () => {
      isCancelled = true;
    };
  }, [deepResearchStateByPdf, fetchDeepResearchTrace, pdfId, setDeepResearchStateForPdf]);

  const currentDeepResearchState = pdfId
    ? deepResearchStateByPdf[pdfId] || createEmptyDeepResearchState()
    : createEmptyDeepResearchState();
  const currentResearchTaskId = currentDeepResearchState.task?.taskId || '';
  const currentResearchTaskStatus = currentDeepResearchState.task?.status || '';
  const currentResearchPollError = currentDeepResearchState.pollError || '';

  useEffect(() => {
    if (
      !pdfId ||
      !currentResearchTaskId ||
      TERMINAL_RESEARCH_STATUSES.includes(currentResearchTaskStatus) ||
      ['awaiting_plan_review', 'awaiting_final_review'].includes(currentResearchTaskStatus) ||
      currentResearchPollError
    ) {
      return undefined;
    }

    let isCancelled = false;
    const targetPdfId = pdfId;
    const timerId = setTimeout(async () => {
      try {
        const response = await apiService.getResearchTask(currentResearchTaskId);
        const nextTask = normalizeResearchTask(response?.task);
        if (isCancelled) {
          return;
        }
        if (response?.status !== 'success' || !nextTask) {
          throw new Error(response?.message || '深度研究任务状态刷新失败');
        }

        setDeepResearchStateForPdf(targetPdfId, (prev) => {
          if ((prev.task?.taskId || '') !== currentResearchTaskId) {
            return prev;
          }

          return {
            ...prev,
            task: nextTask,
            pollError: '',
            isCreating: false,
            isCancelling: false,
          };
        });

        if (TERMINAL_RESEARCH_STATUSES.includes(nextTask.status)) {
          fetchDeepResearchTrace(targetPdfId, nextTask.traceId);
        }
      } catch (error) {
        if (isCancelled) {
          return;
        }

        setDeepResearchStateForPdf(targetPdfId, (prev) => {
          if ((prev.task?.taskId || '') !== currentResearchTaskId) {
            return prev;
          }

          return {
            ...prev,
            pollError: error?.response?.data?.message || error?.message || '深度研究任务状态刷新失败。',
            isCreating: false,
            isCancelling: false,
          };
        });
      }
    }, RESEARCH_POLL_INTERVAL_MS);

    return () => {
      isCancelled = true;
      clearTimeout(timerId);
    };
  }, [
    currentResearchPollError,
    currentResearchTaskId,
    currentResearchTaskStatus,
    fetchDeepResearchTrace,
    pdfId,
    setDeepResearchStateForPdf,
  ]);

  const handleSendMessage = useCallback((message) => {
    if (!pdfId || isChatLoading(pdfId)) return;

    setActiveTab('chat');
    setMessages((prev) => [...prev, { role: 'user', content: message }]);

    const controller = startChatRequest(pdfId);
    if (!controller) return;

    const history = messages.slice(-6).map((item) => ({
      role: item.role === 'ai' ? 'assistant' : item.role,
      content: item.content,
    }));

    apiService
      .sendMessage(message, pdfId, history, deconstructData?.paper_skeleton || null, controller.signal)
      .then((response) => {
        const content = response?.reply ?? response?.message ?? response?.data?.reply ?? '暂无回复';
        const sentenceSourceMap = response?.sentenceSourceMap ?? response?.data?.sentenceSourceMap ?? [];
        const ragSources = response?.rag_sources ?? response?.data?.rag_sources ?? [];
        setMessages((prev) => [...prev, {
          role: 'ai',
          content,
          sentenceSourceMap,
          rag_sources: ragSources,
        }]);
      })
      .catch((error) => {
        if (error.name === 'CanceledError' || error.message === 'canceled') {
          return;
        }

        const errMsg = error?.response?.data?.message ?? error?.message ?? '请求失败，请稍后重试';
        setMessages((prev) => [
          ...prev,
          { role: 'ai', content: `抱歉，处理您的请求时出现了错误：${errMsg}` },
        ]);
      })
      .finally(() => {
        finishChatRequest(pdfId);
      });
  }, [deconstructData, finishChatRequest, isChatLoading, messages, pdfId, startChatRequest]);

  const handleAbortChat = useCallback((targetPdfId) => {
    const wasAborted = abortChatRequest(targetPdfId);
    if (!wasAborted) return;
    setMessages((prev) => [...prev, { role: 'ai', isSystem: true, content: '本次回答已由用户取消。' }]);
  }, [abortChatRequest]);

  const handleDeleteChatMessage = useCallback((index) => {
    setMessages((prev) => {
      const targetMessage = prev[index];
      if (!targetMessage) return prev;

      const indexesToDelete = [index];
      if (targetMessage.role === 'user' && prev[index + 1]?.role === 'ai') {
        indexesToDelete.push(index + 1);
      }
      if (targetMessage.role === 'ai' && prev[index - 1]?.role === 'user') {
        indexesToDelete.push(index - 1);
      }

      return prev.filter((_, currentIndex) => !indexesToDelete.includes(currentIndex));
    });
  }, []);

  const handleExplain = useCallback((content, role = 'user', isSyncOnly = false, sourceMeta = null) => {
    if (role === 'user' && !isSyncOnly) {
      handleSendMessage(`请解释以下内容：${content}`);
      return;
    }

    setMessages((prev) => [
      ...prev,
      {
        role,
        content,
        id: Date.now(),
        sourceAnchorId: sourceMeta?.sourceAnchorId || null,
        sourcePageIndex: sourceMeta?.sourcePageIndex ?? null,
        sourceText: sourceMeta?.sourceText || '',
        sourceActionId: sourceMeta?.sourceActionId || null,
        sourceActionLabel: sourceMeta?.sourceActionLabel || '',
      },
    ]);
  }, [handleSendMessage]);

  const handleJumpToSource = useCallback(async (message) => {
    const pageIndex = Number.isFinite(message?.sourcePageIndex)
      ? message.sourcePageIndex
      : Number.isFinite(message?.pageIndex)
        ? message.pageIndex
        : null;
    const anchorId = message?.sourceAnchorId || message?.sectionId || message?.sourceId || null;
    const targetPdfId = `${message?.pdfId ?? ''}`.trim();

    if (!anchorId && !Number.isFinite(pageIndex)) {
      return false;
    }

    if (targetPdfId && targetPdfId !== pdfId) {
      const hasTargetPaper = papersList.some((paper) => `${paper?.id ?? ''}`.trim() === targetPdfId);
      if (!hasTargetPaper) {
        return false;
      }

      const didRestore = await restorePaperState(targetPdfId);
      if (!didRestore) {
        return false;
      }
    } else if (Number.isFinite(pageIndex) && !pdfId) {
      return false;
    }

    setAppMode('reader');
    if (Number.isFinite(pageIndex)) {
      jumpToPage(pageIndex);
    }

    if (anchorId) {
      setFocusedSourceRequest({
        anchorId,
        token: Date.now(),
      });
    }
    return true;
  }, [jumpToPage, papersList, pdfId, restorePaperState]);

  const handleSaveChatToNote = useCallback((index) => {
    const message = messages[index];
    if (!message) return;

    let question = '';
    let answer = '';

    if (message.role === 'user') {
      question = message.content;
      const nextMessage = messages[index + 1];
      answer = nextMessage?.role === 'ai' ? nextMessage.content : '等待 AI 回答中...';
    } else {
      answer = message.content;
      const previousMessage = messages[index - 1];
      question = previousMessage?.role === 'user' ? previousMessage.content : '提问内容定位失败';
    }

    const sourceMessage =
      message.sourceAnchorId
        ? message
        : message.role === 'user'
          ? messages[index + 1]
          : messages[index - 1];

    addNote({
      text: question,
      aiInterpretation: answer,
      pageNumber: -1,
      sourceAnchorId: sourceMessage?.sourceAnchorId || null,
      sourcePageIndex: sourceMessage?.sourcePageIndex ?? null,
      sourceActionId: sourceMessage?.sourceActionId || null,
      sourceActionLabel: sourceMessage?.sourceActionLabel || '',
    });

    window.alert('已将该对话内容收藏至“学术笔记”中。');
  }, [addNote, messages]);

  const handleCaptureChatArtifact = useCallback((index) => {
    const message = messages[index];
    if (!message) {
      return;
    }

    let question = '';
    let answer = '';

    if (message.role === 'user') {
      question = message.content;
      const nextMessage = messages[index + 1];
      answer = nextMessage?.role === 'ai' ? nextMessage.content : message.content;
    } else {
      answer = message.content;
      const previousMessage = messages[index - 1];
      question = previousMessage?.role === 'user' ? previousMessage.content : '未关联到上一条提问';
    }

    const sourceMessage =
      message.sourceAnchorId
        ? message
        : message.role === 'user'
          ? messages[index + 1]
          : messages[index - 1];

    captureArtifact({
      kind: 'chat-answer',
      title: question.length > 36 ? `${question.slice(0, 36)}...` : question,
      summary: answer,
      content: `### 提问\n${question}\n\n### 回答\n${answer}`,
      sourceMessageId: `${message.id ?? index}`,
      pageIndex: sourceMessage?.sourcePageIndex ?? null,
      sourceAnchorId: sourceMessage?.sourceAnchorId || null,
      sourceActionId: sourceMessage?.sourceActionId || null,
      sourceActionLabel: sourceMessage?.sourceActionLabel || '',
      tags: ['chat', 'qa'],
    });
  }, [captureArtifact, messages]);

  const handleCaptureWorkbenchArtifact = useCallback((artifactInput) => {
    captureArtifact(artifactInput);
  }, [captureArtifact]);

  const handleDeleteNote = useCallback((noteId) => {
    setNotes((prev) => prev.filter((item) => item.id !== noteId));
  }, [setNotes]);

  const handleCaptureNoteToWorkbench = useCallback((note) => {
    if (!note) {
      return;
    }

    captureArtifact({
      kind: 'margin-note',
      title: (note.text || '边注卡片').slice(0, 36),
      summary: note.aiInterpretation || note.text || '暂无摘要',
      content: `### 原文片段\n${note.text || '暂无原文'}\n\n### 边注解释\n${note.aiInterpretation || '暂无解释'}`,
      pageIndex: note.sourcePageIndex ?? note.pageNumber ?? null,
      sourceAnchorId: note.sourceAnchorId || null,
      sourceActionId: note.sourceActionId || null,
      sourceActionLabel: note.sourceActionLabel || '',
      tags: ['note', 'margin'],
    });
  }, [captureArtifact]);

  const handleSaveArtifactAsNote = useCallback((artifact) => {
    if (!artifact) {
      return;
    }

    addNote({
      text: artifact.title || artifact.summary || '工作台卡片',
      aiInterpretation: artifact.userNote || artifact.summary || artifact.content || '暂无解释',
      pageNumber: Number.isFinite(artifact.pageIndex) ? artifact.pageIndex : -1,
      sourceAnchorId: artifact.sourceAnchorId || null,
      sourcePageIndex: artifact.pageIndex ?? null,
      sourceActionId: artifact.sourceActionId || null,
      sourceActionLabel: artifact.sourceActionLabel || '',
    });
  }, [addNote]);

  const handleReadingProgressChange = useCallback((readingProgress) => {
    setSocraticSession((prev) =>
      normalizeSocraticSession(
        {
          ...prev,
          pdfId: pdfId ?? prev?.pdfId ?? null,
          readingProgress,
        },
        pdfId ?? prev?.pdfId ?? null,
      ),
    );
  }, [pdfId]);

  const handleStartSocratic = useCallback(async (readingProgress) => {
    if (!deconstructData?.paper_skeleton) {
      throw new Error('请先完成“篇章解构”，系统需要论文结构内容。');
    }
    if (!pdfId) {
      throw new Error('请先上传并选择一篇论文。');
    }

    setTaskActive('socraticLoading', true);
    try {
      const normalizedProgress =
        readingProgress?.trim() || '已阅读摘要与引言，正在继续梳理论文的方法设计、实验结果与关键结论。';
      const response = await apiService.startSocraticSession(
        pdfId,
        deconstructData.paper_skeleton,
        normalizedProgress,
      );

      if (response?.status !== 'success') {
        throw new Error(response?.message || '启动引导学习失败');
      }

      setSocraticSession(
        normalizeSocraticSession(
          {
            pdfId,
            started: true,
            readingProgress: normalizedProgress,
            intro: response?.intro || '',
            totalQuestions: response?.totalQuestions || SOCRATIC_TOTAL_QUESTIONS,
            currentIndex: response?.currentIndex || 1,
            currentQuestion: response?.currentQuestion || '',
            turns: [],
            finalSummary: '',
            reviewSuggestions: [],
            isComplete: false,
          },
          pdfId,
        ),
      );
    } finally {
      setTaskActive('socraticLoading', false);
    }
  }, [deconstructData, pdfId, setTaskActive]);

  const handleSubmitSocraticAnswer = useCallback(async (userAnswer) => {
    if (!deconstructData?.paper_skeleton) {
      throw new Error('请先完成“篇章解构”，系统需要论文结构内容。');
    }
    if (!pdfId) {
      throw new Error('请先上传并选择一篇论文。');
    }

    const currentSession = normalizeSocraticSession(socraticSession, pdfId);
    if (!currentSession.started || !currentSession.currentQuestion) {
      throw new Error('请先开始引导学习。');
    }

    setTaskActive('socraticLoading', true);
    try {
      const response = await apiService.answerSocraticSession(
        pdfId,
        deconstructData.paper_skeleton,
        currentSession.readingProgress,
        currentSession.currentIndex,
        currentSession.currentQuestion,
        userAnswer,
        currentSession.turns,
      );

      if (response?.status !== 'success') {
        throw new Error(response?.message || '提交回答失败');
      }

      const nextTurn = {
        index: currentSession.currentIndex,
        question: currentSession.currentQuestion,
        answer: userAnswer,
        masteryLevel: response?.evaluation?.masteryLevel || '一般',
        feedback: response?.evaluation?.feedback || '',
        hint: response?.evaluation?.hint || '',
        coveredAspects: response?.evaluation?.coveredAspects || [],
        missingAspects: response?.evaluation?.missingAspects || [],
        evidenceQuality: response?.evaluation?.evidenceQuality || {},
      };

      setSocraticSession(
        normalizeSocraticSession(
          {
            ...currentSession,
            turns: [...currentSession.turns, nextTurn],
            currentIndex: response?.isComplete
              ? currentSession.totalQuestions
              : response?.nextIndex || currentSession.currentIndex + 1,
            currentQuestion: response?.isComplete ? '' : response?.nextQuestion || '',
            finalSummary: response?.isComplete ? response?.finalSummary || '' : '',
            reviewSuggestions: response?.isComplete ? response?.reviewSuggestions || [] : currentSession.reviewSuggestions,
            isComplete: Boolean(response?.isComplete),
            started: true,
          },
          pdfId,
        ),
      );
    } finally {
      setTaskActive('socraticLoading', false);
    }
  }, [deconstructData, pdfId, setTaskActive, socraticSession]);

  const handleRestartSocratic = useCallback(async () => {
    if (!pdfId) return;
    if (!window.confirm('确定重新开始这一篇论文的引导式学习吗？当前作答记录将被清空。')) return;

    try {
      const db = await initDB();
      await db.delete('sessionStore', pdfId);
      setSocraticSession(createEmptySocraticSession(pdfId));
    } catch (error) {
      console.error('Failed to reset Socratic session.', error);
      window.alert('重新开始失败，请稍后再试。');
    }
  }, [pdfId]);

  const requestPageTranslation = useCallback(async ({
    pageIndex,
    pageText,
    pageLayout = null,
    force = false,
  }) => {
    if (!pdfId) return;

    const excludedZones = deconstructData?.translationLayoutIndex?.[pageIndex]?.excludedZones || [];
    const shouldPreferPlainTranslation = shouldPreferPlainPageTranslation({
      excludedZones,
    });
    const {
      sourceText,
      requestPayloadPageLayout,
      translationSourceText,
      shouldMarkEmpty,
    } = preparePageTranslationRequest({
      pageText,
      pageLayout,
      excludedZones,
      preferPlain: shouldPreferPlainTranslation,
    });
    const expectsStructuredResponse = Boolean(requestPayloadPageLayout?.blocks?.length);
    const requestPlan = planPageTranslationState({
      translationState: translationStateRef.current,
      pdfId,
      pageIndex,
      sourceText,
      pageLayout,
      excludedZones,
      force,
      expectsStructuredResponse,
      shouldMarkEmpty,
      hasActiveRequest: Boolean(translationRequestsRef.current[pageIndex]),
    });

    commitTranslationState(requestPlan.nextState);

    if (!requestPlan.shouldRequest || !translationSourceText) {
      return;
    }

    const previousRequest = translationRequestsRef.current[pageIndex];
    if (previousRequest?.controller) {
      previousRequest.controller.abort();
    }

    const requestToken = ++translationRequestSequenceRef.current;
    latestTranslationTokensRef.current[pageIndex] = requestToken;
    const isCurrentRequest = () => latestTranslationTokensRef.current[pageIndex] === requestToken;
    const clearCurrentRequest = () => {
      if (translationRequestsRef.current[pageIndex]?.token === requestToken) {
        delete translationRequestsRef.current[pageIndex];
      }
    };
    const runTranslateRequest = async (requestText, requestLayout, timeoutMs = 90000) => {
      const controller = new AbortController();
      translationRequestsRef.current[pageIndex] = { token: requestToken, controller };
      return apiService.translatePage(
        pdfId,
        pageIndex,
        requestText,
        deconstructData?.paper_skeleton || null,
        requestLayout,
        {
          timeoutMs,
          signal: controller.signal,
        },
      );
    };

    try {
      let response;
      if (expectsStructuredResponse) {
        try {
          response = await runTranslateRequest(
            translationSourceText,
            requestPayloadPageLayout,
            STRUCTURED_TRANSLATION_TIMEOUT_MS,
          );
        } catch {
          if (!isCurrentRequest()) {
            return;
          }
          response = await runTranslateRequest(translationSourceText, null);
        }
      } else {
        response = await runTranslateRequest(translationSourceText, requestPayloadPageLayout);
      }

      if (!isCurrentRequest()) {
        return;
      }

      const translatedText = response?.translatedText ?? response?.data?.translatedText ?? '';
      const translatedBlocks = Array.isArray(response?.translatedBlocks) ? response.translatedBlocks : [];
      const renderMode =
        response?.renderMode ||
        (translatedBlocks.length > 0 && pageLayout?.blocks?.length ? 'overlay' : 'plain');

      commitTranslationState((prev) => {
        if (prev?.pdfId !== pdfId || !isCurrentRequest()) {
          return prev;
        }

        return {
          ...prev,
          currentPage: pageIndex,
          pages: {
            ...prev.pages,
            [pageIndex]: normalizeTranslationPage({
              ...prev.pages?.[pageIndex],
              sourceText,
              translatedBlocks,
              renderMode,
              pageLayout: pageLayout || prev.pages?.[pageIndex]?.pageLayout || null,
              excludedZones,
              translatedText: translatedText || '暂无译文',
              status: 'success',
              error: '',
              updatedAt: Date.now(),
            }),
          },
        };
      });
    } catch (error) {
      if (!isCurrentRequest()) {
        return;
      }

      const errorMessage = error?.response?.data?.message ?? error?.message ?? '当前页翻译失败，请稍后重试。';
      commitTranslationState((prev) => {
        if (prev?.pdfId !== pdfId || !isCurrentRequest()) {
          return prev;
        }

        return {
          ...prev,
          currentPage: pageIndex,
          pages: {
            ...prev.pages,
            [pageIndex]: normalizeTranslationPage({
              ...prev.pages?.[pageIndex],
              sourceText,
              translatedBlocks: [],
              renderMode: 'plain',
              pageLayout: pageLayout || prev.pages?.[pageIndex]?.pageLayout || null,
              excludedZones,
              translatedText: '',
              status: 'error',
              error: errorMessage,
              updatedAt: Date.now(),
            }),
          },
        };
      });
    } finally {
      clearCurrentRequest();
    }
  }, [commitTranslationState, deconstructData, pdfId]);

  const handlePdfPageChange = useCallback((pageChange) => {
    const pageIndex =
      typeof pageChange === 'number'
        ? pageChange
        : Number.isFinite(pageChange?.pageIndex)
          ? pageChange.pageIndex
          : 0;
    const totalPages =
      typeof pageChange === 'object' && Number.isFinite(pageChange?.totalPages)
        ? pageChange.totalPages
        : pdfPageState.totalPages;

    setPdfPageState({
      pageIndex,
      totalPages,
    });
    currentPageTextRef.current = {
      pageIndex,
      pageText: '',
      pageLayout: null,
    };
    commitTranslationState((prev) => {
      const baseState = prev?.pdfId === pdfId ? prev : createEmptyTranslationState(pdfId);
      return baseState.currentPage === pageIndex ? baseState : { ...baseState, currentPage: pageIndex };
    });
  }, [commitTranslationState, pdfId, pdfPageState.totalPages, setPdfPageState]);

  const handlePageTextExtracted = useCallback(({
    pageIndex,
    pageText,
    pageLayout = null,
  }) => {
    const excludedZones = deconstructData?.translationLayoutIndex?.[pageIndex]?.excludedZones || [];
    currentPageTextRef.current = { pageIndex, pageText, pageLayout };
    commitTranslationState((prev) => {
      const baseState = prev?.pdfId === pdfId ? prev : createEmptyTranslationState(pdfId);
      const existingPage = normalizeTranslationPage(baseState.pages?.[pageIndex] || {});

      return {
        ...baseState,
        currentPage: pageIndex,
        pages: {
          ...baseState.pages,
          [pageIndex]: normalizeTranslationPage({
            ...existingPage,
            sourceText: pageText || existingPage.sourceText,
            pageLayout: pageLayout || existingPage.pageLayout || null,
            excludedZones: excludedZones.length > 0 ? excludedZones : existingPage.excludedZones || [],
          }),
        },
      };
    });

    if (isTranslated) {
      requestPageTranslation({ pageIndex, pageText, pageLayout });
    }
  }, [commitTranslationState, deconstructData, isTranslated, pdfId, requestPageTranslation]);

  const handleRetryTranslation = useCallback(() => {
    const currentPage = translationState.currentPage ?? currentPageTextRef.current.pageIndex ?? 0;
    const pagePayload =
      currentPageTextRef.current.pageIndex === currentPage
        ? currentPageTextRef.current
        : {
            pageIndex: currentPage,
            pageText: translationState.pages?.[currentPage]?.sourceText || '',
            pageLayout: translationState.pages?.[currentPage]?.pageLayout || null,
          };

    requestPageTranslation({ ...pagePayload, force: true });
  }, [requestPageTranslation, translationState.currentPage, translationState.pages]);

  const handleHighlightsChange = useCallback((nextHighlights) => {
    setPdfHighlights(nextHighlights);
    initDB().then((db) => {
      if (pdfId) {
        db.put('highlightStore', nextHighlights, pdfId);
      }
    });
  }, [pdfId, setPdfHighlights]);

  const currentTranslationPage = translationState.pages?.[translationState.currentPage] || null;
  const activeTabMeta = workspaceTabs.find((tab) => tab.id === activeTab) || workspaceTabs[0];
  const ActiveTabIcon = activeTabMeta.icon;
  const activeWorkspaceSection =
    workspaceTabSections.find((section) => section.id === activeWorkspaceSectionId) || workspaceTabSections[0];
  const visibleWorkspaceTabs = workspaceTabs.filter((tab) => activeWorkspaceSection.tabIds.includes(tab.id));
  const currentPaperStatus = pdfFile ? (isDeconstructing ? '解析中' : '已载入') : '待上传';
  const currentResearchProgress = Math.round((currentDeepResearchState.task?.progress || 0) * 100);
  const paperOutlineModel = buildPaperOutlineModel(deconstructData);
  const paperOutlineItems = paperOutlineModel.items;
  const currentOutlineItem = resolveCurrentOutlineItem(paperOutlineItems, pdfPageState.pageIndex);
  const visibleOutlineItems = getVisibleOutlineItems(paperOutlineItems, collapsedOutlineIds, outlineQuery);
  const readingProgress = calculateReadingProgress(pdfPageState);
  const modelName =
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_MODEL_NAME) || DEFAULT_MODEL_NAME;
  const currentWorkflowStage =
    workflowStages.find((stage) => stage.id === getWorkflowStageId(activeTab)) || workflowStages[0];
  const currentWorkflowStageIndex = workflowStages.findIndex((stage) => stage.id === currentWorkflowStage.id);
  const workflowStepSummary = workflowStages.map((stage, index) => {
    const isCurrent = stage.id === currentWorkflowStage.id;
    const isCompleted = index < currentWorkflowStageIndex;
    return {
      ...stage,
      status: isCurrent ? 'current' : isCompleted ? 'completed' : 'upcoming',
    };
  });
  const latestUserMessage = [...messages].reverse().find((message) => message.role === 'user');
  const latestAiMessage = [...messages].reverse().find((message) => message.role === 'ai' && !message.isSystem);
  const latestResearchFinding =
    currentDeepResearchState.task?.findings?.[
      (currentDeepResearchState.task?.findings?.length || 0) - 1
    ] || null;
  const latestArtifact = workbenchCards[workbenchCards.length - 1] || null;
  const readingContext = {
    sectionTitle: currentOutlineItem?.label || deconstructData?.paper_structure?.title || pdfFileName || '当前论文',
    pageLabel: pdfFile ? `第 ${pdfPageState.pageIndex + 1} 页` : '尚未打开 PDF',
    sourceSnippet: clampSnippet(
      latestUserMessage?.sourceText ||
        currentOutlineItem?.preview ||
        currentTranslationPage?.sourceText ||
        latestAiMessage?.content ||
        latestResearchFinding?.summary ||
        latestArtifact?.summary ||
        latestArtifact?.title,
    ),
    latestQuestion: clampSnippet(latestUserMessage?.content || currentDeepResearchState.questionDraft || ''),
    latestAnswer: clampSnippet(latestAiMessage?.content || latestResearchFinding?.summary || ''),
    artifactCount: workbenchCards.length + notes.length,
  };
  const nextActionSuggestions = buildReadingWorkflowSuggestions({
    hasPdf: Boolean(pdfFile),
    activeTab,
    isDeconstructing,
    latestUserMessage,
    deepResearchState: currentDeepResearchState,
    artifactCount: readingContext.artifactCount,
    pdfId,
  });
  const primaryNextActionSuggestion = getPrimaryReadingWorkflowSuggestion(nextActionSuggestions);

  const handleReadingWorkflowAction = useCallback((suggestion) => {
    const action = suggestion?.action;
    if (!action) return;

    if (action.type === 'agent') {
      setAppMode('agent');
      return;
    }

    const targetTabId = action.tabId;
    if (!targetTabId) return;

    if (action.type === 'workbench' || targetTabId === 'notes') {
      setIsWorkbenchCollapsed(false);
    }
    setActiveWorkspaceSectionId(getWorkspaceSectionId(targetTabId));
    setActiveTab(targetTabId);
  }, []);

  return (
    <>
      <CodeExecutionApprovalCenter />
      <LibrarySidebar
        isOpen={isLibraryOpen}
        onClose={() => setIsLibraryOpen(false)}
        papers={papersList}
        currentPdfId={pdfId}
        currentStudyProgressSnapshot={currentStudyProgressSnapshot}
        currentPage={pdfFile ? pdfPageState.pageIndex + 1 : 0}
        currentTotalPages={pdfPageState.totalPages || 0}
        onSelectPaper={handleSelectPaper}
        onDeletePaper={handleDeletePaper}
      />

      {isAboutOpen && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/35 p-4 backdrop-blur-sm">
          <div className="theme-panel theme-border w-full max-w-md rounded-lg border shadow-2xl">
            <div className="theme-border flex items-center justify-between border-b px-5 py-4">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-md bg-pixiu text-white">
                  <Info size={18} />
                </div>
                <div>
                  <h2 className="theme-text-primary text-base font-bold">关于 Pixiu</h2>
                  <p className="theme-text-muted text-xs">学术论文 AI 阅读与批判分析工作台</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsAboutOpen(false)}
                className="theme-icon-button rounded-md px-2 py-1 text-sm"
              >
                关闭
              </button>
            </div>
            <div className="space-y-3 p-5 text-sm">
              <div className="theme-card-soft flex items-center justify-between rounded-md p-3">
                <span className="theme-text-secondary">版本号</span>
                <span className="theme-text-primary font-semibold">v{APP_VERSION}</span>
              </div>
              <div className="theme-card-soft flex items-center justify-between rounded-md p-3">
                <span className="theme-text-secondary">当前模型</span>
                <span className="theme-text-primary font-semibold">{modelName}</span>
              </div>
              <div className="theme-card-soft flex items-center justify-between rounded-md p-3">
                <span className="theme-text-secondary">前端框架</span>
                <span className="theme-text-primary font-semibold">React 19 + Vite</span>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="theme-app-shell flex h-screen flex-col font-sans">
        <Navbar
          isReady={isAiReady}
          theme={theme}
          onFileUpload={handlePdfUpload}
          onToggleTheme={handleToggleTheme}
          onToggleLibrary={() => setIsLibraryOpen(true)}
          currentFileName={pdfFileName}
          onOpenAbout={() => setIsAboutOpen(true)}
          appMode={appMode}
          onAppModeChange={setAppMode}
        />

        <main className="workspace-main flex min-h-0 flex-1 overflow-hidden">
          {appMode === 'agent' ? (
            <AgentWorkspace
              paperLibrary={papersList}
              activePaperId={pdfId || ''}
              onCaptureArtifact={handleCaptureWorkbenchArtifact}
              onJumpToSource={handleJumpToSource}
            />
          ) : (
          <>
          <aside
            className={`workspace-sidebar theme-panel theme-border hidden shrink-0 flex-col border-r transition-[width] duration-200 xl:flex ${
              isSidebarCollapsed ? 'w-14' : 'w-64'
            }`}
          >
            <div className="theme-border border-b p-3">
              <div className="flex items-center justify-between gap-2">
                {!isSidebarCollapsed && (
                  <div className="min-w-0">
                    <h2 className="theme-text-primary text-sm font-bold">论文导航</h2>
                    <span className="theme-text-muted text-[10px]">
                      第 {pdfFile ? pdfPageState.pageIndex + 1 : 0} / {pdfPageState.totalPages || 0} 页
                    </span>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => setIsSidebarCollapsed((value) => !value)}
                  className="theme-button-secondary flex h-8 w-8 shrink-0 items-center justify-center rounded-md"
                  title={isSidebarCollapsed ? '展开左侧栏' : '收起左侧栏'}
                >
                  {isSidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
                </button>
              </div>
              {!isSidebarCollapsed && (
                <>
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-500">
                      {currentPaperStatus}
                    </span>
                    <span className="theme-text-muted text-[10px]">阅读进度 {readingProgress}%</span>
                  </div>
                  <div className="theme-input mt-3 flex items-center gap-2 rounded-md px-3 py-2 text-xs">
                    <Search size={14} className="theme-text-muted" />
                    <span className="theme-text-muted">搜索目录 / 笔记 / 论文</span>
                  </div>
                </>
              )}
            </div>

            <div className={`flex-1 overflow-y-auto ${isSidebarCollapsed ? 'p-2' : 'p-4'}`}>
              {isSidebarCollapsed ? (
                <div className="flex flex-col items-center gap-3">
                  <button
                    type="button"
                    className="theme-button-secondary flex h-9 w-9 items-center justify-center rounded-md"
                    title="当前论文"
                  >
                    <FileText size={16} />
                  </button>
                  <button
                    type="button"
                    className="theme-button-secondary flex h-9 w-9 items-center justify-center rounded-md"
                    title="篇章目录"
                  >
                    <LayoutDashboard size={16} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsLibraryOpen(true)}
                    className="theme-button-secondary flex h-9 w-9 items-center justify-center rounded-md"
                    title="论文库"
                  >
                    <BookOpen size={16} />
                  </button>
                </div>
              ) : (
                <>
              <section className="mb-5">
                <div className="theme-text-muted mb-2 flex items-center justify-between text-xs font-bold">
                  <span>当前论文</span>
                  <span>{notes.length} 条笔记</span>
                </div>
                <div className="theme-card-soft rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    <FileText size={16} className="mt-0.5 shrink-0 text-pixiu" />
                    <div className="min-w-0">
                      <p className="theme-text-primary line-clamp-2 text-sm font-semibold">
                        {pdfFileName || '尚未上传论文'}
                      </p>
                      <p className="theme-text-muted mt-1 text-xs">
                        {pdfFile ? '可在中间阅读器中划词解释、翻译和批判阅读' : '请先上传 PDF 开始工作'}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200/70">
                    <div
                      className="h-full rounded-full bg-pixiu"
                      style={{ width: `${readingProgress}%` }}
                    />
                  </div>
                </div>
              </section>

              <section className="mb-5">
                <div className="mb-2 flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="theme-text-muted text-xs font-bold">篇章目录</div>
                    {currentOutlineItem && (
                      <div className="theme-text-muted mt-0.5 truncate text-[10px]">
                        当前：{currentOutlineItem.label}
                      </div>
                    )}
                  </div>
                  <span className={`outline-source-badge outline-source-badge-${paperOutlineModel.source}`}>
                    {paperOutlineModel.sourceLabel}
                  </span>
                </div>

                <label className="theme-input mb-2 flex items-center gap-2 rounded-md px-2 py-1.5 text-xs">
                  <Search size={13} className="theme-text-muted shrink-0" />
                  <input
                    value={outlineQuery}
                    onChange={(event) => setOutlineQuery(event.target.value)}
                    className="theme-text-primary min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-slate-400"
                    placeholder="搜索标题、页码或摘要"
                    aria-label="搜索篇章目录"
                  />
                </label>

                <div className="outline-tree text-xs">
                  {visibleOutlineItems.map((item) => {
                    const isCollapsed = Boolean(collapsedOutlineIds[item.id]);
                    const isCurrent = currentOutlineItem?.id === item.id;
                    const isCurrentPath = currentOutlineItem?.ancestorIds?.includes(item.id);

                    return (
                      <div
                        key={item.id}
                        className="outline-tree-row"
                        style={{ paddingLeft: `${(item.level - 1) * 12}px` }}
                      >
                        {item.hasChildren ? (
                          <button
                            type="button"
                            className="outline-collapse-toggle"
                            onClick={() => toggleOutlineCollapse(item.id)}
                            aria-label={isCollapsed ? '展开子章节' : '收起子章节'}
                            aria-expanded={!isCollapsed || Boolean(outlineQuery)}
                          >
                            {isCollapsed && !outlineQuery ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                          </button>
                        ) : (
                          <span className="outline-collapse-spacer" />
                        )}

                        <button
                          type="button"
                          className={`outline-tree-item ${
                            isCurrent ? 'outline-tree-item-current' : ''
                          } ${isCurrentPath ? 'outline-tree-item-path' : ''}`}
                          onClick={() => handleSelectOutlineItem(item)}
                          title={[
                            item.label,
                            item.sourceLabel ? `来源：${item.sourceLabel}` : '',
                            Number.isFinite(item.confidence) ? `置信度：${Math.round(item.confidence * 100)}%` : '',
                            item.preview,
                          ].filter(Boolean).join('\n')}
                          aria-current={isCurrent ? 'true' : undefined}
                        >
                          <span className="min-w-0 flex-1 truncate">
                            {renderHighlightedText(item.label, outlineQuery)}
                          </span>
                          <span className="outline-page-label">
                            {item.pageLabel || item.meta}
                          </span>
                        </button>
                      </div>
                    );
                  })}

                  {paperOutlineItems.length > 0 && visibleOutlineItems.length === 0 && (
                    <div className="theme-empty-state rounded-md px-3 py-2 text-center text-xs">
                      没有匹配的篇章
                    </div>
                  )}

                  {paperOutlineItems.length === 0 && (
                    <div className="theme-empty-state rounded-md px-3 py-3 text-center text-xs">
                      <p>
                        {isDeconstructing
                          ? '正在解析论文结构...'
                          : deconstructData
                            ? '未能识别可导航的论文结构'
                            : '上传论文后显示真实论文结构'}
                      </p>
                      {!isDeconstructing && (
                        <button
                          type="button"
                          onClick={() => setActiveTab('deconstruct')}
                          className="mt-2 text-[11px] font-semibold text-pixiu"
                        >
                          篇章解构
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </section>

              <section>
                <div className="theme-text-muted mb-2 flex items-center justify-between text-xs font-bold">
                  <span>最近论文</span>
                  <button type="button" onClick={() => setIsLibraryOpen(true)} className="text-pixiu">
                    全部
                  </button>
                </div>
                <div className="space-y-2">
                  {papersList.slice(0, 4).map((paper) => (
                    <button
                      key={paper.id}
                      type="button"
                      onClick={() => handleSelectPaper(paper.id)}
                      className={`theme-border w-full rounded-lg border p-2 text-left transition hover:border-pixiu/40 ${
                        paper.id === pdfId ? 'bg-pixiu/10' : 'theme-panel'
                      }`}
                    >
                      <span className="theme-text-primary line-clamp-2 text-xs font-semibold">{paper.filename}</span>
                      <span className="theme-text-muted mt-1 block text-[10px]">
                        {new Date(paper.timestamp).toLocaleDateString()}
                      </span>
                    </button>
                  ))}
                  {papersList.length === 0 && (
                    <div className="theme-empty-state rounded-lg p-3 text-center text-xs">论文库暂无内容</div>
                  )}
                </div>
              </section>
                </>
              )}
            </div>
          </aside>

          <section className="min-w-0 flex-1 overflow-hidden">
            <Group orientation="vertical">
              <Panel
                defaultSize={76}
                minSize={42}
              >
                <Group orientation="horizontal">
                  <Panel defaultSize={58} minSize={34}>
                    <div className="pdf-stage relative flex h-full flex-col p-3">
                  <div className="workspace-pdf-header theme-panel theme-border mb-2 flex h-10 shrink-0 items-center justify-between rounded-md border px-3 text-sm">
                    <div className="flex min-w-0 items-center gap-2">
                      <FileText size={16} className="text-pixiu" />
                      <span className="theme-text-primary truncate font-medium">
                        {pdfFileName || '上传论文后在此阅读 PDF'}
                      </span>
                    </div>
                    <div className="theme-text-muted hidden items-center gap-3 text-xs md:flex">
                      <span>
                        第 {pdfFile ? pdfPageState.pageIndex + 1 : 0} / {pdfPageState.totalPages || 0} 页
                      </span>
                      <span>阅读 {readingProgress}%</span>
                      <span>划词解释</span>
                      {isTranslated && <span className="text-pixiu">译文已开启</span>}
                    </div>
                  </div>

                  <div className="pdf-viewer-shell flex-1 overflow-hidden rounded-md">
                    <PdfViewer
                      fileUrl={pdfFile}
                      pdfId={pdfId}
                      paperSkeleton={deconstructData?.paper_skeleton || null}
                      theme={theme}
                      translationLayoutIndex={deconstructData?.translationLayoutIndex || {}}
                      onSelection={handleExplain}
                      onSaveNote={addNote}
                      initialHighlights={pdfHighlights}
                      onHighlightsChange={handleHighlightsChange}
                      onPageChange={handlePdfPageChange}
                      onPageTextExtracted={handlePageTextExtracted}
                      targetPageIndex={targetPageIndex}
                      targetPageJumpToken={targetPageJumpToken}
                      focusedSourceAnchorId={focusedSourceRequest.anchorId}
                      focusedSourceAnchorToken={focusedSourceRequest.token}
                    />
                  </div>
                    </div>
                  </Panel>

                  <Separator className="group relative w-1.5 transition-all hover:bg-pixiu/10">
                    <div className="app-separator-line absolute inset-y-0 left-1/2 w-[2px] -translate-x-1/2 transition-colors group-hover:bg-pixiu/40" />
                  </Separator>

                  <Panel defaultSize={42} minSize={32}>
                    <div className="panel-shell flex h-full flex-col">
                      <div className="theme-panel theme-border flex shrink-0 flex-col border-b">
                        <div className="workspace-top-panels">
                          <div className="workspace-top-panels-collapsed">
                            <div className="flex min-w-0 items-center gap-2">
                              <Info size={16} className="text-pixiu" />
                              <div className="min-w-0">
                                <h2 className="theme-text-primary truncate text-sm font-bold">辅助导航</h2>
                                <div className="theme-text-muted truncate text-[11px]">
                                  {activeTabMeta.label} · {currentWorkflowStage.label}
                                </div>
                              </div>
                            </div>
                            <div className="workspace-top-panels-status">
                              {currentDeepResearchState.task ? `研究 ${currentResearchProgress}%` : `${visibleWorkspaceTabs.length} 项功能`}
                            </div>
                          </div>

                          <div className="workspace-top-panels-expanded">
                            <div className="px-3 pb-2">
                              <div className="workflow-stage-strip flex gap-2 overflow-x-auto">
                                {workflowStepSummary.map((stage) => {
                                  const isActiveStage = stage.id === currentWorkflowStage.id;
                                  return (
                                    <button
                                      key={stage.id}
                                      type="button"
                                      onClick={() => {
                                        const targetTabId = stage.tabIds[0];
                                        setActiveWorkspaceSectionId(getWorkspaceSectionId(targetTabId));
                                        setActiveTab(targetTabId);
                                      }}
                                      className={`workflow-stage-chip ${stage.status} ${
                                        isActiveStage ? 'workflow-stage-chip-active' : ''
                                      }`}
                                      title={stage.description}
                                    >
                                      <span className="workflow-stage-chip-label">{stage.shortLabel}</span>
                                      <span className="workflow-stage-chip-title">{stage.label}</span>
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                            <div className="workspace-top-summary-grid px-3 pb-2">
                              <div className="workflow-context-card theme-card-soft rounded-xl p-3">
                                <div className="flex items-center justify-between gap-2">
                                  <div className="theme-text-primary text-xs font-semibold">当前研读上下文</div>
                                  <span className="theme-text-muted text-[10px]">{readingContext.artifactCount} 条已沉淀</span>
                                </div>
                                <div className="mt-2 grid gap-1 text-[11px] leading-5 theme-text-secondary">
                                  <div className="flex gap-2">
                                    <span className="workflow-context-label">章节</span>
                                    <span className="truncate">{readingContext.sectionTitle}</span>
                                  </div>
                                  <div className="flex gap-2">
                                    <span className="workflow-context-label">位置</span>
                                    <span>{readingContext.pageLabel}</span>
                                  </div>
                                  {readingContext.sourceSnippet && (
                                    <div className="flex gap-2">
                                      <span className="workflow-context-label">原文</span>
                                      <span className="min-w-0 flex-1 truncate">{readingContext.sourceSnippet}</span>
                                    </div>
                                  )}
                                  {readingContext.latestQuestion && (
                                    <div className="flex gap-2">
                                      <span className="workflow-context-label">问题</span>
                                      <span className="min-w-0 flex-1 truncate">{readingContext.latestQuestion}</span>
                                    </div>
                                  )}
                                </div>
                              </div>
                              <div className="workflow-profile-card theme-card rounded-xl p-3">
                                <div className="flex items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <div className="theme-text-primary text-xs font-semibold">背景补课偏好</div>
                                    <div className="theme-text-secondary mt-1 text-[11px] leading-5">
                                      这里决定补课的深浅、目标和当前卡点，生成背景补课时会直接作为上下文透传。
                                    </div>
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setActiveWorkspaceSectionId(getWorkspaceSectionId('background'));
                                      setActiveTab('background');
                                    }}
                                    className="workflow-next-action"
                                  >
                                    去补课
                                  </button>
                                </div>
                                <div className="mt-3">
                                  <BackgroundReaderProfileEditor
                                    value={backgroundReaderProfile}
                                    onChange={setBackgroundReaderProfile}
                                    compact
                                  />
                                </div>
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {backgroundReaderProfileSummary.map((item) => (
                                    <span key={item} className="workbench-kind-chip">
                                      {item}
                                    </span>
                                  ))}
                                </div>
                              </div>
                              <div className="workflow-next-card theme-card rounded-xl p-3">
                                <div className="flex items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <div className="theme-text-primary text-xs font-semibold">
                                      {primaryNextActionSuggestion?.title || nextActionSuggestions[0]?.title}
                                    </div>
                                    <div className="theme-text-secondary mt-1 text-[11px] leading-5">
                                      {primaryNextActionSuggestion?.description || nextActionSuggestions[0]?.description}
                                    </div>
                                  </div>
                                  <div className="workflow-next-badge whitespace-nowrap text-[10px] font-semibold">
                                    推荐下一步
                                  </div>
                                </div>
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {nextActionSuggestions.map((suggestion, index) => (
                                    <button
                                      key={`${suggestion.title}-${suggestion.label || index}`}
                                      type="button"
                                      disabled={!suggestion.action}
                                      onClick={() => handleReadingWorkflowAction(suggestion)}
                                      className={`workflow-next-action ${
                                        suggestion.tone === 'primary' ? 'workflow-next-action-primary' : ''
                                      }`}
                                    >
                                      {suggestion.label || suggestion.title}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            </div>
                            <div className="px-3 pb-2">
                              <button
                                type="button"
                                onClick={() => setIsWorkspaceNavExpanded((current) => !current)}
                                className={`workspace-nav-toggle ${isWorkspaceNavExpanded ? 'workspace-nav-toggle-active' : ''}`}
                                title={isWorkspaceNavExpanded ? '收起功能导航' : '展开功能导航'}
                              >
                                <span>功能导航</span>
                                <span className="workspace-nav-toggle-meta">
                                  {visibleWorkspaceTabs.length} 项
                                </span>
                                <ChevronDown
                                  size={14}
                                  className={`transition-transform ${isWorkspaceNavExpanded ? 'rotate-180' : ''}`}
                                />
                              </button>
                            </div>
                            {isWorkspaceNavExpanded && (
                              <>
                                <div className="workspace-section-tabs flex flex-wrap gap-2 px-3 pb-2">
                                  {workspaceTabSections.map((section) => {
                                    const isActiveSection = section.id === activeWorkspaceSection.id;
                                    return (
                                      <button
                                        key={section.id}
                                        type="button"
                                        onClick={() => {
                                          setActiveWorkspaceSectionId(section.id);
                                          if (!section.tabIds.includes(activeTab)) {
                                            setActiveTab(section.tabIds[0]);
                                          }
                                        }}
                                        className={`workspace-section-tab ${
                                          isActiveSection ? 'workspace-section-tab-active' : ''
                                        }`}
                                        title={section.description}
                                      >
                                        {section.label}
                                      </button>
                                    );
                                  })}
                                </div>
                                <div
                                  ref={workspaceTabsRef}
                                  className="workspace-tabs flex gap-1 overflow-x-auto px-2 pb-2"
                                  onWheel={handleWorkspaceTabsWheel}
                                  title="鼠标悬停后滚轮可横向切换功能标签"
                                >
                                  {visibleWorkspaceTabs.map((item) => {
                                    const Icon = item.icon;
                                    const isActive = activeTab === item.id;
                                    return (
                                      <button
                                        key={item.id}
                                        type="button"
                                        data-active-tab={isActive ? 'true' : undefined}
                                        onClick={() => setActiveTab(item.id)}
                                        className={`workspace-tab-button flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold transition ${
                                          isActive ? 'workspace-tab-button-active' : ''
                                        }`}
                                      >
                                        <Icon size={14} />
                                        {item.label}
                                      </button>
                                    );
                                  })}
                                </div>
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="min-h-0 flex-1 overflow-hidden">
                    {activeTab === 'chat' && (
                      <ChatPanel
                        messages={messages}
                        onSendMessage={handleSendMessage}
                        onDeleteMessage={handleDeleteChatMessage}
                        onSaveToNote={handleSaveChatToNote}
                        onCaptureArtifact={handleCaptureChatArtifact}
                        onJumpToSource={handleJumpToSource}
                        onAbortChat={() => handleAbortChat(pdfId)}
                        isLoading={isChatLoading(pdfId)}
                        contextTitle={readingContext.sectionTitle}
                        contextSummary={`${readingContext.pageLabel}${readingContext.sourceSnippet ? ` · ${readingContext.sourceSnippet}` : ''}`}
                        nextActionHint={primaryNextActionSuggestion?.label || nextActionSuggestions[0]?.title}
                      />
                    )}

                    {activeTab === 'socratic' && (
                      <SocraticQuestionsPanel
                        hasPaperContext={!!deconstructData?.paper_skeleton}
                        isLoading={isSocraticLoading}
                        session={socraticSession}
                        onReadingProgressChange={handleReadingProgressChange}
                        onStart={handleStartSocratic}
                        onSubmitAnswer={handleSubmitSocraticAnswer}
                        onRestart={handleRestartSocratic}
                      />
                    )}

                    {activeTab === 'background' && (
                      <BackgroundKnowledgePanel
                        data={backgroundKnowledgeData}
                        isLoading={isBackgroundKnowledgeLoading}
                        hasPaperContext={!!deconstructData?.paper_skeleton}
                        onGenerate={handleGenerateBackgroundKnowledge}
                        readerProfile={backgroundReaderProfile}
                        onCaptureArtifact={handleCaptureWorkbenchArtifact}
                        onJumpToSource={handleJumpToSource}
                      />
                    )}

                    {activeTab === 'deep-research' && (
                      <DeepResearchPanel
                        pdfFileName={pdfFileName}
                        paperStructure={deconstructData?.paper_structure || null}
                        questionDraft={currentDeepResearchState.questionDraft}
                        task={currentDeepResearchState.task}
                        errorMessage={currentDeepResearchState.errorMessage}
                        pollError={currentDeepResearchState.pollError}
                        isCreating={currentDeepResearchState.isCreating}
                        isCancelling={currentDeepResearchState.isCancelling}
                        briefPreview={currentDeepResearchState.briefPreview}
                        briefConstraintsDraft={currentDeepResearchState.briefConstraintsDraft}
                        isPreviewingBrief={currentDeepResearchState.isPreviewingBrief}
                        briefError={currentDeepResearchState.briefError}
                        traceSummary={currentDeepResearchState.traceSummary}
                        traceError={currentDeepResearchState.traceError}
                        isTraceLoading={currentDeepResearchState.isTraceLoading}
                        isTracePanelEnabled={Boolean(import.meta.env?.DEV)}
                        allowExternalSearch={Boolean(currentDeepResearchState.allowExternalSearch)}
                        onQuestionChange={handleDeepResearchQuestionChange}
                        onStart={handleStartResearchTask}
                        onPreviewBrief={handlePreviewResearchBrief}
                        onBriefConstraintsChange={handleDeepResearchBriefConstraintsChange}
                        onAcceptBrief={() => handleStartResearchTask({ useBriefPreview: true })}
                        onAllowExternalSearchChange={(value) => setDeepResearchStateForPdf(pdfId, (prev) => ({ ...prev, allowExternalSearch: Boolean(value) }))}
                        onRefresh={handleRefreshResearchTask}
                        onCancel={handleCancelResearchTask}
                        onReviewPlan={handleReviewResearchPlan}
                        onReviewFinal={handleReviewResearchFinal}
                        onRefreshTrace={() => fetchDeepResearchTrace(pdfId, currentDeepResearchState.task?.traceId)}
                        onCaptureArtifact={handleCaptureWorkbenchArtifact}
                        onJumpToSource={handleJumpToSource}
                      />
                    )}

                    {activeTab === 'deconstruct' && (
                      <PaperAnalysis
                        data={deconstructData}
                        isLoading={isDeconstructing}
                        outlineItems={paperOutlineItems}
                        pdfId={pdfId}
                        onSelectOutlineItem={handleSelectOutlineItem}
                        onCaptureArtifact={handleCaptureWorkbenchArtifact}
                      />
                    )}

                    {activeTab === 'analysis' && (
                      <CriticalAnalysisPanel
                        data={analysisData}
                        onAnalyze={handleStartAnalysis}
                        isLoading={isAnalyzing}
                        onCaptureArtifact={handleCaptureWorkbenchArtifact}
                        onJumpToSource={handleJumpToSource}
                      />
                    )}

                    {activeTab === 'translation' && (
                      <TranslationPanel
                        pdfId={pdfId}
                        pdfFileName={pdfFileName}
                        currentPage={translationState.currentPage}
                        pageData={currentTranslationPage}
                        onRetry={handleRetryTranslation}
                        onCaptureArtifact={handleCaptureWorkbenchArtifact}
                      />
                    )}

                    {activeTab === 'paper-writer' && (
                      <PaperWriterPanel
                        apiService={apiService}
                        onSaveToWorkbench={handleCaptureWorkbenchArtifact}
                      />
                    )}

                    {activeTab === 'notes' && (
                      <div className="theme-panel-muted flex h-full flex-col items-center justify-center p-8 text-center">
                        <div className="theme-panel theme-border w-full max-w-2xl rounded-3xl border p-8 shadow-sm">
                          <div className="theme-text-primary text-lg font-bold">资产总览入口</div>
                          <div className="theme-text-secondary mt-3 text-sm leading-7">
                            P3 已经把长期资产主阵地移动到底部工作台。
                            这里保留为概览入口，方便你查看当前论文已经沉淀的卡片与边注规模。
                          </div>
                          <div className="mt-6 grid gap-3 text-left md:grid-cols-2">
                            <div className="theme-card-soft rounded-2xl p-4">
                              <div className="theme-text-primary text-sm font-semibold">Workbench Cards</div>
                              <div className="theme-text-secondary mt-1 text-sm">{workbenchCards.length} 张</div>
                            </div>
                            <div className="theme-card-soft rounded-2xl p-4">
                              <div className="theme-text-primary text-sm font-semibold">Margin Notes</div>
                              <div className="theme-text-secondary mt-1 text-sm">{notes.length} 条</div>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => setIsWorkbenchCollapsed(false)}
                            className="mt-6 rounded-full bg-pixiu px-4 py-2 text-sm font-semibold text-white"
                          >
                            展开底部工作台
                          </button>
                        </div>
                      </div>
                    )}
                    </div>
                    </div>
                  </Panel>
                </Group>
              </Panel>

              <Separator className="group relative h-2 transition-all hover:bg-pixiu/10">
                <div className="app-separator-line absolute left-0 right-0 top-1/2 h-[2px] -translate-y-1/2 transition-colors group-hover:bg-pixiu/40" />
              </Separator>

              <Panel
                panelRef={workbenchPanelRef}
                defaultSize={WORKBENCH_EXPANDED_SIZE}
                minSize={WORKBENCH_COLLAPSED_SIZE}
                onResize={(size) => {
                  const shouldCollapse = size <= WORKBENCH_COLLAPSE_THRESHOLD;
                  setIsWorkbenchCollapsed((prev) => (prev === shouldCollapse ? prev : shouldCollapse));
                }}
              >
                <BottomWorkbench
                  pdfFileName={pdfFileName}
                  cards={workbenchCards}
                  notes={notes}
                  isCollapsed={isWorkbenchCollapsed}
                  onToggleCollapsed={handleToggleWorkbenchCollapsed}
                  onJumpToArtifactSource={handleJumpToSource}
                  onJumpToNoteSource={handleJumpToSource}
                  onRemoveArtifact={removeArtifact}
                  onToggleArtifactPinned={toggleArtifactPinned}
                  onUpdateArtifact={updateArtifact}
                  onCaptureNote={handleCaptureNoteToWorkbench}
                  onSaveArtifactAsNote={handleSaveArtifactAsNote}
                  onDeleteNote={handleDeleteNote}
                />
              </Panel>
            </Group>
          </section>
          </>
          )}
        </main>
      </div>
    </>
  );
}

