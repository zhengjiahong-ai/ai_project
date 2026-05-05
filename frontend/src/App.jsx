import React, { useCallback, useEffect, useRef, useState } from 'react';
import { openDB } from 'idb';
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
  Trash2,
} from 'lucide-react';
import { Group, Panel, Separator } from 'react-resizable-panels';

import BackgroundKnowledgePanel from './components/BackgroundKnowledgePanel.jsx';
import ChatPanel from './components/ChatPanel';
import CriticalAnalysisPanel from './components/CriticalAnalysisPanel';
import DeepResearchPanel from './components/DeepResearchPanel.jsx';
import LibrarySidebar from './components/LibrarySidebar';
import Navbar from './components/Navbar';
import PaperAnalysis from './components/PaperAnalysis';
import PdfToolbar from './components/PdfToolbar';
import PdfViewer from './components/PdfViewer';
import SocraticQuestionsPanel from './components/SocraticQuestionsPanel';
import TranslationPanel from './components/TranslationPanel';
import MarkdownContent from './components/MarkdownContent';
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
  TERMINAL_RESEARCH_STATUSES,
  createEmptyDeepResearchState,
  normalizeResearchTask,
} from './components/deepResearchPanelModel.js';
import appVersionRaw from '../../VERSION?raw';

const APP_VERSION = appVersionRaw.trim() || '0.0.0';
const DEFAULT_MODEL_NAME = 'DeepSeek V4';

const WELCOME_MESSAGE = {
  role: 'ai',
  content: '您好！我是您的 AI 学术助手。上传论文后，您可以直接划选正文句子进行解释、批判阅读，并保留对话历史。',
};

const workspaceTabs = [
  { id: 'chat', label: '问答', icon: MessageSquare },
  { id: 'deconstruct', label: '篇章解构', icon: LayoutDashboard },
  { id: 'analysis', label: '批判阅读', icon: BarChart3 },
  { id: 'translation', label: '逐页翻译', icon: BookOpen },
  { id: 'background', label: '背景补课', icon: Network },
  { id: 'socratic', label: '引导学习', icon: Sparkles },
  { id: 'deep-research', label: '深度研究', icon: Search },
  { id: 'notes', label: '笔记', icon: Bookmark },
];

const DEFAULT_ACTIVE_TAB = 'chat';
const THEME_STORAGE_KEY = 'pixiu-theme';
const DEFAULT_BACKGROUND_KNOWLEDGE_LEVEL = '一般';
const RESEARCH_POLL_INTERVAL_MS = 1500;
const STRUCTURED_TRANSLATION_TIMEOUT_MS = 15000;

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
      const label = `${section.title || section.name || section.section || `Section ${index + 1}`}`.trim();
      const pageMeta = normalizeOutlinePage(section);
      const explicitLevel = coerceFiniteNumber(section.level ?? section.nestedLevel);
      const headingNumber = `${section.headingNumber || section.number || ''}`.trim();

      return {
        id: section.id || section.key || `section-${index + 1}`,
        label,
        level: Number.isFinite(explicitLevel)
          ? explicitLevel
          : getOutlineLevel(headingNumber || label),
        parentId: section.parentId || null,
        headingNumber,
        meta: pageMeta.pageLabel || section.type || `${index + 1}`,
        preview: section.preview || section.summary || '',
        source: 'pdf',
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

const calculateReadingProgress = ({ pageIndex = 0, totalPages = 0 } = {}) =>
  totalPages ? Math.min(100, Math.round(((pageIndex + 1) / totalPages) * 100)) : 0;

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

const initDB = async () =>
  openDB('PixiuAcademicDB_v6', 5, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('pdfStore')) db.createObjectStore('pdfStore');
      if (!db.objectStoreNames.contains('historyStore')) db.createObjectStore('historyStore');
      if (!db.objectStoreNames.contains('analysisStore')) db.createObjectStore('analysisStore');
      if (!db.objectStoreNames.contains('notesStore')) db.createObjectStore('notesStore');
      if (!db.objectStoreNames.contains('deconstructStore')) db.createObjectStore('deconstructStore');
      if (!db.objectStoreNames.contains('libraryStore')) db.createObjectStore('libraryStore', { keyPath: 'id' });
      if (!db.objectStoreNames.contains('highlightStore')) db.createObjectStore('highlightStore');
      if (!db.objectStoreNames.contains('sessionStore')) db.createObjectStore('sessionStore');
      if (!db.objectStoreNames.contains('translationStore')) db.createObjectStore('translationStore');
      if (!db.objectStoreNames.contains('backgroundKnowledgeStore')) db.createObjectStore('backgroundKnowledgeStore');
    },
  });

const normalizeHistoryMessages = (messages = []) =>
  messages.map((message, index) => ({
    id: message.id ?? `${message.timestamp ?? 'local'}-${index}`,
    role: message.role === 'assistant' ? 'ai' : message.role,
    content: message.content,
    timestamp: message.timestamp ?? null,
  }));

const createReadyMessage = (filename) => [
  {
    role: 'ai',
    content: `已成功加载论文：${filename}。我现在可以为您分析这篇文章了。`,
  },
];

const resolveStoredPdfRecord = (storedValue) => {
  if (!storedValue) {
    return null;
  }

  if (storedValue instanceof Blob) {
    return {
      blob: storedValue,
      name: storedValue.name ?? null,
    };
  }

  if (storedValue.blob instanceof Blob) {
    return {
      blob: storedValue.blob,
      name: storedValue.name ?? storedValue.blob.name ?? null,
    };
  }

  return null;
};

export default function App() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') {
      return 'light';
    }

    return localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light';
  });
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfFileName, setPdfFileName] = useState(null);
  const [pdfId, setPdfId] = useState(null);
  const [isAiReady, setIsAiReady] = useState(true);
  const [messages, setMessages] = useState([WELCOME_MESSAGE]);
  const [activeTab, setActiveTab] = useState('chat');
  const [analysisData, setAnalysisData] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [backgroundKnowledgeData, setBackgroundKnowledgeData] = useState(null);
  const [backgroundKnowledgeLevel, setBackgroundKnowledgeLevel] = useState(DEFAULT_BACKGROUND_KNOWLEDGE_LEVEL);
  const [isBackgroundKnowledgeLoading, setIsBackgroundKnowledgeLoading] = useState(false);
  const [isRestored, setIsRestored] = useState(false);
  const [notes, setNotes] = useState([]);
  const [isTranslated, setIsTranslated] = useState(false);
  const [isDeconstructing, setIsDeconstructing] = useState(false);
  const [deconstructData, setDeconstructData] = useState(null);
  const [socraticSession, setSocraticSession] = useState(createEmptySocraticSession());
  const [isSocraticLoading, setIsSocraticLoading] = useState(false);
  const [loadingPapers, setLoadingPapers] = useState({});
  const [pdfHighlights, setPdfHighlights] = useState([]);
  const [translationState, setTranslationState] = useState(createEmptyTranslationState());
  const [deepResearchStateByPdf, setDeepResearchStateByPdf] = useState({});
  const [papersList, setPapersList] = useState([]);
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [outlineQuery, setOutlineQuery] = useState('');
  const [collapsedOutlineIds, setCollapsedOutlineIds] = useState({});
  const [pdfPageState, setPdfPageState] = useState({
    pageIndex: 0,
    totalPages: 0,
  });
  const [targetPageIndex, setTargetPageIndex] = useState(null);
  const [targetPageJumpToken, setTargetPageJumpToken] = useState(0);

  const abortControllers = useRef({});
  const translationRequestsRef = useRef({});
  const translationRequestSequenceRef = useRef(0);
  const latestTranslationTokensRef = useRef({});
  const translationStateRef = useRef(createEmptyTranslationState());
  const papersListRef = useRef([]);
  const currentPdfIdRef = useRef(null);
  const workspaceTabsRef = useRef(null);
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
    setOutlineQuery('');
    setCollapsedOutlineIds({});
  }, [pdfId]);

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
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    if (activeTab !== 'translation') {
      lastNonTranslationTabRef.current = activeTab;
    }
  }, [activeTab]);

  const handleToggleTheme = useCallback(() => {
    setTheme((currentTheme) => (currentTheme === 'dark' ? 'light' : 'dark'));
  }, []);

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

  const fetchRemoteHistory = useCallback(async (sessionId, fallbackMessages = []) => {
    try {
      const response = await apiService.getChatHistory(sessionId);
      const remoteMessages = normalizeHistoryMessages(response?.messages || []);
      if (remoteMessages.length > 0) {
        const db = await initDB();
        await db.put('historyStore', remoteMessages, sessionId);
        return remoteMessages;
      }
    } catch (error) {
      console.warn('Failed to load remote chat history, using local cache instead.', error);
    }

    return fallbackMessages.length > 0 ? fallbackMessages : [WELCOME_MESSAGE];
  }, []);

  const restorePaperState = useCallback(async (targetPdfId, entryList = null) => {
    const db = await initDB();
    const [
      savedPdf,
      savedMessages,
      savedAnalysis,
      savedDeconstruct,
      savedNotes,
      savedHighlights,
      savedSocraticSession,
      savedTranslationState,
      savedBackgroundKnowledge,
    ] = await Promise.all([
      db.get('pdfStore', targetPdfId),
      db.get('historyStore', targetPdfId),
      db.get('analysisStore', targetPdfId),
      db.get('deconstructStore', targetPdfId),
      db.get('notesStore', targetPdfId),
      db.get('highlightStore', targetPdfId),
      db.get('sessionStore', targetPdfId),
      db.get('translationStore', targetPdfId),
      db.get('backgroundKnowledgeStore', targetPdfId),
    ]);

    const resolvedPdf = resolveStoredPdfRecord(savedPdf);
    if (!resolvedPdf) {
      return false;
    }

    const currentEntries = Array.isArray(entryList) ? entryList : papersListRef.current;
    const libraryEntry = currentEntries.find((paper) => paper.id === targetPdfId);
    const savedPageIndex = Number.isFinite(libraryEntry?.currentPage)
      ? Math.max(0, libraryEntry.currentPage - 1)
      : 0;
    const savedTotalPages = Number.isFinite(libraryEntry?.totalPages)
      ? Math.max(0, libraryEntry.totalPages)
      : 0;
    const fallbackMessages =
      savedMessages && savedMessages.length > 0
        ? savedMessages
        : createReadyMessage(libraryEntry?.filename ?? resolvedPdf.name ?? '当前论文');

    const nextMessages = await fetchRemoteHistory(targetPdfId, fallbackMessages);

    setPdfId(targetPdfId);
    setPdfFile(URL.createObjectURL(resolvedPdf.blob));
    setPdfFileName(libraryEntry?.filename ?? resolvedPdf.name ?? null);
    setDeconstructData(savedDeconstruct || null);
    setNotes(savedNotes || []);
    setAnalysisData(savedAnalysis || null);
    setBackgroundKnowledgeData(savedBackgroundKnowledge || null);
    setBackgroundKnowledgeLevel(normalizeBackgroundKnowledgeLevel(savedBackgroundKnowledge?.user_knowledge_level));
    setMessages(nextMessages);
    setPdfHighlights(savedHighlights || []);
    setSocraticSession(normalizeSocraticSession(savedSocraticSession, targetPdfId));
    commitTranslationState(normalizeTranslationState(savedTranslationState, targetPdfId));
    setIsTranslated(false);
    currentPageTextRef.current = { pageIndex: 0, pageText: '', pageLayout: null };
    setPdfPageState({ pageIndex: savedPageIndex, totalPages: savedTotalPages });
    setTargetPageIndex(savedPageIndex > 0 ? savedPageIndex : null);
    if (savedPageIndex > 0) {
      setTargetPageJumpToken((token) => token + 1);
    }
    setActiveTab((currentTab) =>
      currentTab === 'translation' ? lastNonTranslationTabRef.current || DEFAULT_ACTIVE_TAB : currentTab,
    );
    localStorage.setItem('lastPdfId', targetPdfId);

    return true;
  }, [commitTranslationState, fetchRemoteHistory]);

  const handlePdfUpload = useCallback(async (file) => {
    if (!file) return;

    setPdfFileName(file.name);
    setPdfFile(URL.createObjectURL(file));
    setIsAiReady(false);
    setIsDeconstructing(true);

    try {
      const response = await apiService.uploadPdf(file);
      if (!response || response.status !== 'success') {
        throw new Error(response?.message || '论文上传失败');
      }

      const readyMessages = createReadyMessage(file.name);
      const newEntry = {
        id: response.pdfId,
        title: response.title || file.name,
        filename: file.name,
        authors: normalizeAuthors(response.authors),
        parseStatus: response.ragIndexed === false ? '索引异常' : '已解析',
        sectionCount: response.paper_structure?.sections?.length || 0,
        readingProgress: 0,
        currentPage: 0,
        totalPages: 0,
        timestamp: Date.now(),
        updatedAt: Date.now(),
      };

      const db = await initDB();
      await Promise.all([
        db.put('pdfStore', file, response.pdfId),
        db.put('deconstructStore', response, response.pdfId),
        db.put('analysisStore', null, response.pdfId),
        db.put('historyStore', readyMessages, response.pdfId),
        db.put('highlightStore', [], response.pdfId),
        db.put('libraryStore', newEntry),
        db.delete('sessionStore', response.pdfId),
        db.delete('translationStore', response.pdfId),
        db.delete('backgroundKnowledgeStore', response.pdfId),
      ]);

      setPdfId(response.pdfId);
      setDeconstructData(response);
      setAnalysisData(null);
      setBackgroundKnowledgeData(null);
      setBackgroundKnowledgeLevel(DEFAULT_BACKGROUND_KNOWLEDGE_LEVEL);
      setNotes([]);
      setMessages(readyMessages);
      setPdfHighlights([]);
      setSocraticSession(createEmptySocraticSession(response.pdfId));
      commitTranslationState(createEmptyTranslationState(response.pdfId));
      setIsTranslated(false);
      currentPageTextRef.current = { pageIndex: 0, pageText: '', pageLayout: null };
      setPdfPageState({ pageIndex: 0, totalPages: 0 });
      setTargetPageIndex(null);
      setActiveTab('deconstruct');
      setPapersList((prev) => [newEntry, ...prev.filter((paper) => paper.id !== response.pdfId)]);
      localStorage.setItem('lastPdfId', response.pdfId);

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
      setBackgroundKnowledgeLevel(DEFAULT_BACKGROUND_KNOWLEDGE_LEVEL);
      commitTranslationState(createEmptyTranslationState());
      setIsTranslated(false);
      currentPageTextRef.current = { pageIndex: 0, pageText: '', pageLayout: null };
      setPdfPageState({ pageIndex: 0, totalPages: 0 });
      setTargetPageIndex(null);
      const uploadErrorMessage = formatUploadErrorMessage(error);
      window.setTimeout(() => {
        window.alert(uploadErrorMessage);
      }, 0);
    } finally {
      setIsAiReady(true);
      setIsDeconstructing(false);
    }
  }, [commitTranslationState]);

  useEffect(() => {
    const restoreSession = async () => {
      try {
        const savedTab = localStorage.getItem('activeTab');
        if (savedTab && savedTab !== 'translation') {
          setActiveTab(savedTab);
        }

        const db = await initDB();
        const list = await db.getAll('libraryStore');
        const sortedList = [...list].sort((left, right) => right.timestamp - left.timestamp);
        setPapersList(sortedList);

        const savedPdfId = localStorage.getItem('lastPdfId');
        if (savedPdfId) {
          const restored = await restorePaperState(savedPdfId, sortedList);
          if (!restored && sortedList.length > 0) {
            await restorePaperState(sortedList[0].id, sortedList);
          }
        } else if (sortedList.length > 0) {
          await restorePaperState(sortedList[0].id, sortedList);
        }
      } catch (error) {
        console.error('Failed to restore local session.', error);
      } finally {
        setIsRestored(true);
      }
    };

    restoreSession();
  }, [restorePaperState]);

  const handleSelectPaper = useCallback(async (targetPdfId) => {
    setIsAiReady(false);
    try {
      await restorePaperState(targetPdfId);
    } catch (error) {
      console.error('Failed to load selected paper.', error);
    } finally {
      setIsAiReady(true);
    }
  }, [restorePaperState]);

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

  const handleToggleOutlineCollapse = useCallback((outlineId) => {
    setCollapsedOutlineIds((current) => ({
      ...current,
      [outlineId]: !current[outlineId],
    }));
  }, []);

  const handleSelectOutlineItem = useCallback((item) => {
    setActiveTab('deconstruct');
    if (Number.isFinite(item.pageIndex)) {
      setTargetPageIndex(item.pageIndex);
      setTargetPageJumpToken((token) => token + 1);
    }
  }, []);

  const handleDeletePaper = useCallback(async (targetPdfId) => {
    if (!window.confirm('确定移除这篇论文及其所有关联聊天、笔记和引导学习记录吗？')) return;

    try {
      const db = await initDB();
      await Promise.all([
        db.delete('pdfStore', targetPdfId),
        db.delete('historyStore', targetPdfId),
        db.delete('analysisStore', targetPdfId),
        db.delete('notesStore', targetPdfId),
        db.delete('deconstructStore', targetPdfId),
        db.delete('libraryStore', targetPdfId),
        db.delete('highlightStore', targetPdfId),
        db.delete('sessionStore', targetPdfId),
        db.delete('translationStore', targetPdfId),
        db.delete('backgroundKnowledgeStore', targetPdfId),
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
        setNotes([]);
        setDeconstructData(null);
        setAnalysisData(null);
        setBackgroundKnowledgeData(null);
        setBackgroundKnowledgeLevel(DEFAULT_BACKGROUND_KNOWLEDGE_LEVEL);
        setPdfHighlights([]);
        setSocraticSession(createEmptySocraticSession());
        commitTranslationState(createEmptyTranslationState());
        setIsTranslated(false);
        currentPageTextRef.current = { pageIndex: 0, pageText: '', pageLayout: null };
        setPdfPageState({ pageIndex: 0, totalPages: 0 });
        setTargetPageIndex(null);
        setActiveTab(DEFAULT_ACTIVE_TAB);
        localStorage.removeItem('lastPdfId');
      }
    } catch (error) {
      console.error('Failed to delete paper.', error);
    }
  }, [commitTranslationState, pdfId]);

  useEffect(() => {
    if (!isRestored || !pdfId) return;

    const saveMessages = async () => {
      try {
        const db = await initDB();
        if (messages && messages.length > 0) {
          await db.put('historyStore', messages, pdfId);
          localStorage.setItem(
            'activeTab',
            activeTab === 'translation' ? lastNonTranslationTabRef.current || DEFAULT_ACTIVE_TAB : activeTab,
          );
        }
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
        await db.put('notesStore', notes, pdfId);
      } catch (error) {
        console.error('Failed to persist notes.', error);
      }
    };

    saveNotes();
  }, [isRestored, notes, pdfId]);

  useEffect(() => {
    if (!isRestored || !pdfId || socraticSession?.pdfId !== pdfId) return;

    const saveSocraticSession = async () => {
      try {
        const db = await initDB();
        const shouldPersist =
          socraticSession.started ||
          socraticSession.isComplete ||
          Boolean((socraticSession.readingProgress || '').trim());

        if (!shouldPersist) {
          await db.delete('sessionStore', pdfId);
          return;
        }

        await db.put(
          'sessionStore',
          {
            ...socraticSession,
            updatedAt: Date.now(),
          },
          pdfId,
        );
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
        await db.put(
          'translationStore',
          {
            ...translationState,
            updatedAt: Date.now(),
          },
          pdfId,
        );
      } catch (error) {
        console.error('Failed to persist translation state.', error);
      }
    };

    saveTranslationState();
  }, [isRestored, pdfId, translationState]);

  useEffect(() => {
    if (!isRestored || !pdfId) return;

    const nextProgress = calculateReadingProgress(pdfPageState);
    const nextCurrentPage = pdfPageState.totalPages ? pdfPageState.pageIndex + 1 : 0;
    const nextTotalPages = pdfPageState.totalPages || 0;
    const updatedAt = Date.now();

    setPapersList((prev) => {
      let didUpdate = false;
      const nextList = prev.map((paper) => {
        if (paper.id !== pdfId) return paper;

        if (
          paper.readingProgress === nextProgress &&
          paper.currentPage === nextCurrentPage &&
          paper.totalPages === nextTotalPages
        ) {
          return paper;
        }

        didUpdate = true;
        return {
          ...paper,
          readingProgress: nextProgress,
          currentPage: nextCurrentPage,
          totalPages: nextTotalPages,
          updatedAt,
        };
      });

      return didUpdate ? nextList : prev;
    });

    const saveLibraryProgress = async () => {
      try {
        const db = await initDB();
        const paper = await db.get('libraryStore', pdfId);
        if (!paper) return;

        await db.put('libraryStore', {
          ...paper,
          readingProgress: nextProgress,
          currentPage: nextCurrentPage,
          totalPages: nextTotalPages,
          updatedAt,
        });
      } catch (error) {
        console.error('Failed to persist library reading progress.', error);
      }
    };

    saveLibraryProgress();
  }, [isRestored, pdfId, pdfPageState]);

  const handleStartAnalysis = useCallback(async () => {
    if (!pdfId) {
      window.alert('请先上传 PDF 文件。');
      return;
    }

    setActiveTab('analysis');
    setIsAnalyzing(true);

    try {
      const response = await apiService.criticalReading(pdfId);
      const payload = response?.analysis ?? response;
      const isSuccess = response?.status === 'success' || payload?.status === 'success' || Boolean(payload);
      if (!isSuccess) {
        throw new Error(response?.message || payload?.message || '批判性阅读失败');
      }

      setAnalysisData(payload);
      const db = await initDB();
      await db.put('analysisStore', payload, pdfId);
    } catch (error) {
      console.error('Failed to run critical reading.', error);
      window.alert(error?.response?.data?.message || error?.message || '批判性阅读失败，请稍后重试。');
    } finally {
      setIsAnalyzing(false);
    }
  }, [pdfId]);

  const handleGenerateBackgroundKnowledge = useCallback(async (selectedLevel = backgroundKnowledgeLevel) => {
    if (!pdfId) {
      window.alert('请先上传 PDF 文件。');
      return;
    }

    setActiveTab('background');
    setIsBackgroundKnowledgeLoading(true);

    try {
      const requestedKnowledgeLevel = normalizeBackgroundKnowledgeLevel(selectedLevel);
      const researchProblem = deconstructData?.paper_structure?.research_problem;
      const coreHypothesis = deconstructData?.paper_structure?.core_hypothesis;
      const paperTopic =
        typeof researchProblem === 'string' && researchProblem.trim()
          ? researchProblem
          : typeof coreHypothesis === 'string' && coreHypothesis.trim()
            ? coreHypothesis
            : null;

      const response = await apiService.backgroundKnowledge({
        pdfId,
        paperSkeleton: deconstructData?.paper_skeleton || null,
        paperStructure: deconstructData?.paper_structure || null,
        paper_topic: paperTopic,
        user_knowledge_level: requestedKnowledgeLevel,
      });

      if (!response || response.status !== 'success') {
        throw new Error(response?.message || '背景补课图谱生成失败');
      }

      setBackgroundKnowledgeData(response);
      setBackgroundKnowledgeLevel(normalizeBackgroundKnowledgeLevel(response?.user_knowledge_level || requestedKnowledgeLevel));
      const db = await initDB();
      await db.put('backgroundKnowledgeStore', response, pdfId);
    } catch (error) {
      console.error('Failed to generate background knowledge graph.', error);
      window.alert(error?.response?.data?.message || error?.message || '背景补课图谱生成失败，请稍后重试。');
    } finally {
      setIsBackgroundKnowledgeLoading(false);
    }
  }, [backgroundKnowledgeLevel, deconstructData, pdfId]);

  const handleDeepResearchQuestionChange = useCallback((nextQuestionDraft) => {
    if (!pdfId) {
      return;
    }

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      questionDraft: nextQuestionDraft,
      errorMessage: '',
    }));
  }, [pdfId, setDeepResearchStateForPdf]);

  const handleStartResearchTask = useCallback(async () => {
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
    }));

    try {
      const response = await apiService.createResearchTask(
        question,
        pdfId,
        deconstructData?.paper_skeleton || null,
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
      }));

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
  }, [deepResearchStateByPdf, deconstructData, pdfId, setDeepResearchStateForPdf]);

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
  }, [deepResearchStateByPdf, pdfId, setDeepResearchStateForPdf]);

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
  }, [deepResearchStateByPdf, pdfId, setDeepResearchStateForPdf]);

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
    pdfId,
    setDeepResearchStateForPdf,
  ]);

  const handleSendMessage = useCallback((message) => {
    if (!pdfId || loadingPapers[pdfId]) return;

    setActiveTab('chat');
    setMessages((prev) => [...prev, { role: 'user', content: message }]);

    const controller = new AbortController();
    abortControllers.current[pdfId] = controller;
    setLoadingPapers((prev) => ({ ...prev, [pdfId]: true }));

    const history = messages.slice(-6).map((item) => ({
      role: item.role === 'ai' ? 'assistant' : item.role,
      content: item.content,
    }));

    apiService
      .sendMessage(message, pdfId, history, deconstructData?.paper_skeleton || null, controller.signal)
      .then((response) => {
        const content = response?.reply ?? response?.message ?? response?.data?.reply ?? '暂无回复';
        setMessages((prev) => [...prev, { role: 'ai', content }]);
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
        setLoadingPapers((prev) => ({ ...prev, [pdfId]: false }));
        delete abortControllers.current[pdfId];
      });
  }, [deconstructData, loadingPapers, messages, pdfId]);

  const handleAbortChat = useCallback((targetPdfId) => {
    const controller = abortControllers.current[targetPdfId];
    if (!controller) return;

    controller.abort();
    setLoadingPapers((prev) => ({ ...prev, [targetPdfId]: false }));
    setMessages((prev) => [...prev, { role: 'ai', isSystem: true, content: '本次回答已由用户取消。' }]);
    delete abortControllers.current[targetPdfId];
  }, []);

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

  const handleExplain = useCallback((content, role = 'user', isSyncOnly = false) => {
    setActiveTab('chat');
    if (role === 'user' && !isSyncOnly) {
      handleSendMessage(`请解释以下内容：${content}`);
      return;
    }

    setMessages((prev) => [...prev, { role, content, id: Date.now() }]);
  }, [handleSendMessage]);

  const handleAddNote = useCallback((noteData) => {
    setNotes((prev) => [
      {
        id: Date.now(),
        ...noteData,
        time: new Date().toLocaleTimeString(),
      },
      ...prev,
    ]);
  }, []);

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

    handleAddNote({
      text: question,
      aiInterpretation: answer,
      pageNumber: -1,
    });

    window.alert('已将该对话内容收藏至“学术笔记”！');
  }, [handleAddNote, messages]);

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

    setIsSocraticLoading(true);
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
      setIsSocraticLoading(false);
    }
  }, [deconstructData, pdfId]);

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

    setIsSocraticLoading(true);
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
      setIsSocraticLoading(false);
    }
  }, [deconstructData, pdfId, socraticSession]);

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

  const handleDynamicExplain = useCallback(() => {
    setActiveTab('chat');
    setMessages((prev) => [
      ...prev,
      {
        role: 'ai',
        content: '功能提示：在左侧 PDF 视窗中直接划选任何不理解的句子或段落，点击弹出的“AI 解释”按钮，我将结合整篇论文上下文为您深入解析。',
      },
    ]);
  }, []);

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
          response = await runTranslateRequest(sourceText, null);
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
  }, [commitTranslationState, pdfId, pdfPageState.totalPages]);

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

  const handleToggleTranslation = useCallback(() => {
    if (!pdfId) {
      window.alert('请先上传 PDF 文件。');
      return;
    }

    if (isTranslated) {
      setIsTranslated(false);
      if (activeTab === 'translation') {
        setActiveTab(lastNonTranslationTabRef.current || DEFAULT_ACTIVE_TAB);
      }
      return;
    }

    if (activeTab !== 'translation') {
      lastNonTranslationTabRef.current = activeTab;
    }

    setIsTranslated(true);
    setActiveTab('translation');
    if (currentPageTextRef.current.pageText) {
      requestPageTranslation(currentPageTextRef.current);
    }
  }, [activeTab, isTranslated, pdfId, requestPageTranslation]);

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
  }, [pdfId]);

  const handleCriticalReading = useCallback(() => {
    if (!pdfId) {
      window.alert('请先上传 PDF 文件。');
      return;
    }

    handleStartAnalysis();
  }, [handleStartAnalysis, pdfId]);

  const currentTranslationPage = translationState.pages?.[translationState.currentPage] || null;
  const activeTabMeta = workspaceTabs.find((tab) => tab.id === activeTab) || workspaceTabs[0];
  const ActiveTabIcon = activeTabMeta.icon;
  const currentPaperStatus = pdfFile ? (isDeconstructing ? '解析中' : '已载入') : '待上传';
  const currentResearchProgress = Math.round((currentDeepResearchState.task?.progress || 0) * 100);
  const paperOutlineModel = buildPaperOutlineModel(deconstructData);
  const paperOutlineItems = paperOutlineModel.items;
  const currentOutlineItem = resolveCurrentOutlineItem(paperOutlineItems, pdfPageState.pageIndex);
  const visibleOutlineItems = getVisibleOutlineItems(paperOutlineItems, collapsedOutlineIds, outlineQuery);
  const readingProgress = calculateReadingProgress(pdfPageState);
  const modelName =
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_MODEL_NAME) || DEFAULT_MODEL_NAME;

  return (
    <>
      <LibrarySidebar
        isOpen={isLibraryOpen}
        onClose={() => setIsLibraryOpen(false)}
        papers={papersList}
        currentPdfId={pdfId}
        currentReadingProgress={readingProgress}
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
        />

        <main className="workspace-main flex min-h-0 flex-1 overflow-hidden">
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
                            onClick={() => handleToggleOutlineCollapse(item.id)}
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
                          title={item.preview ? `${item.label}\n${item.preview}` : item.label}
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
            <Group orientation="horizontal">
              <Panel defaultSize={62} minSize={36}>
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
                      theme={theme}
                      translationLayoutIndex={deconstructData?.translationLayoutIndex || {}}
                      onSelection={handleExplain}
                      onSaveNote={handleAddNote}
                      initialHighlights={pdfHighlights}
                      onHighlightsChange={handleHighlightsChange}
                      onPageChange={handlePdfPageChange}
                      onPageTextExtracted={handlePageTextExtracted}
                      targetPageIndex={targetPageIndex}
                      targetPageJumpToken={targetPageJumpToken}
                    />
                  </div>

                  {pdfFile && (
                    <PdfToolbar
                      onDynamicExplain={handleDynamicExplain}
                      onCriticalReading={handleCriticalReading}
                      onSocraticLearning={() => {
                        setActiveTab('socratic');
                      }}
                      isTranslated={isTranslated}
                      onToggleTranslation={handleToggleTranslation}
                    />
                  )}
                </div>
              </Panel>

              <Separator className="group relative w-1.5 transition-all hover:bg-pixiu/10">
                <div className="app-separator-line absolute inset-y-0 left-1/2 w-[2px] -translate-x-1/2 transition-colors group-hover:bg-pixiu/40" />
              </Separator>

              <Panel defaultSize={38} minSize={28}>
                <div className="panel-shell flex h-full flex-col">
                  <div className="theme-panel theme-border flex shrink-0 flex-col border-b">
                    <div className="flex items-center justify-between gap-3 px-4 py-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <ActiveTabIcon size={16} className="text-pixiu" />
                        <div className="min-w-0">
                          <h2 className="theme-text-primary text-sm font-bold">{activeTabMeta.label}</h2>
                          <p className="theme-text-muted truncate text-[10px]">
                            当前功能沿用原有实现，仅调整外层工作台排版
                          </p>
                        </div>
                      </div>
                      {currentDeepResearchState.task && (
                        <span className="rounded-full bg-pixiu/10 px-2 py-0.5 text-[10px] font-bold text-pixiu">
                          研究 {currentResearchProgress}%
                        </span>
                      )}
                    </div>
                    <div
                      ref={workspaceTabsRef}
                      className="workspace-tabs flex gap-1 overflow-x-auto px-2 pb-2"
                      onWheel={handleWorkspaceTabsWheel}
                      title="鼠标悬停后滚轮可横向切换功能标签"
                    >
                      {workspaceTabs.map((item) => {
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
                  </div>

                  <div className="min-h-0 flex-1 overflow-hidden">
                {activeTab === 'chat' && (
                  <ChatPanel
                    messages={messages}
                    onSendMessage={handleSendMessage}
                    onDeleteMessage={handleDeleteChatMessage}
                    onSaveToNote={handleSaveChatToNote}
                    onAbortChat={() => handleAbortChat(pdfId)}
                    isLoading={!!loadingPapers[pdfId]}
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
                    knowledgeLevel={backgroundKnowledgeLevel}
                    onKnowledgeLevelChange={setBackgroundKnowledgeLevel}
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
                    onQuestionChange={handleDeepResearchQuestionChange}
                    onStart={handleStartResearchTask}
                    onRefresh={handleRefreshResearchTask}
                    onCancel={handleCancelResearchTask}
                  />
                )}

                {activeTab === 'deconstruct' && (
                  <PaperAnalysis data={deconstructData} isLoading={isDeconstructing} />
                )}

                {activeTab === 'analysis' && (
                  <CriticalAnalysisPanel
                    data={analysisData}
                    onAnalyze={handleStartAnalysis}
                    isLoading={isAnalyzing}
                  />
                )}

                {activeTab === 'translation' && (
                  <TranslationPanel
                    pdfFileName={pdfFileName}
                    currentPage={translationState.currentPage}
                    pageData={currentTranslationPage}
                    onRetry={handleRetryTranslation}
                  />
                )}

                {activeTab === 'notes' && (
                  <div className="theme-panel-muted flex flex-1 flex-col overflow-hidden">
                    <div className="theme-panel theme-border border-b p-4 font-bold text-pixiu">📝 学术笔记精华</div>
                    <div className="flex-1 space-y-4 overflow-y-auto p-4">
                      {notes.map((note) => (
                        <div
                          key={note.id}
                          className="theme-card group relative rounded-xl p-4"
                        >
                          <button
                            onClick={() => {
                              if (window.confirm('确定删除这条学术笔记吗？')) {
                                setNotes((prev) => prev.filter((item) => item.id !== note.id));
                              }
                            }}
                            className="theme-danger-button absolute right-2 top-2 rounded-md p-1.5 opacity-0 transition-opacity group-hover:opacity-100"
                            title="删除此笔记"
                          >
                            <Trash2 size={14} />
                          </button>

                          <div className="mb-2 flex justify-between text-[10px] font-bold text-pixiu">
                            <span>PAGE {note.pageNumber + 1}</span>
                            <span>{note.time}</span>
                          </div>
                          <p className="theme-note-quote mb-3 pl-3 text-sm italic">
                            "{note.text}"
                          </p>
                          <div className="theme-markdown-panel rounded-lg p-3">
                            <MarkdownContent>{note.aiInterpretation}</MarkdownContent>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                  </div>
              </div>
              </Panel>
            </Group>
          </section>
        </main>
      </div>
    </>
  );
}
