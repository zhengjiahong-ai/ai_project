import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
const AgentWorkspace = lazy(() => import('./components/agent/AgentWorkspace.jsx'));
import BottomWorkbench from './components/BottomWorkbench.jsx';
import {
  createDefaultReaderProfile,
  summarizeReaderProfile,
} from './components/backgroundKnowledgePanelModel.ts';
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
import { ErrorBoundary } from './components/ErrorBoundary.jsx';
import { ToastProvider, useToast } from './components/Toast.jsx';
import { useAbortableChat } from './hooks/useAbortableChat.js';
import { useChat } from './hooks/useChat.js';
import { useCriticalReading } from './hooks/useCriticalReading.js';
import { useDeepResearch } from './hooks/useDeepResearch.js';
import { usePageTranslation } from './hooks/usePageTranslation.js';
import { usePdfUpload } from './hooks/usePdfUpload.js';
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
} from './components/deepResearchPanelModel.ts';
import {
  buildReadingWorkflowSuggestions,
  getPrimaryReadingWorkflowSuggestion,
} from './components/readingWorkflowModel.ts';
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

import {
  buildPaperOutlineModel,
  clampSnippet,
  coerceFiniteNumber,
  flattenOutlineHierarchy,
  formatCriticalReadingErrorMessage,
  formatUploadErrorMessage,
  getCriticalReadingErrorCode,
  getOutlineLevel,
  getOutlinePageLabel,
  getVisibleOutlineItems,
  normalizeAuthors,
  normalizeBackgroundKnowledgeLevel,
  normalizeOutlinePage,
  normalizeReaderTagList,
  outlineSourceLabels,
  renderHighlightedText,
  resolveCurrentOutlineItem,
  sectionDisplayNames,
} from './utils/appHelpers.js';

const getWorkspaceSectionId = (tabId) =>
  workspaceTabSections.find((section) => section.tabIds.includes(tabId))?.id || workspaceTabSections[0].id;

const getWorkflowStageId = (tabId) =>
  workflowStages.find((stage) => stage.tabIds.includes(tabId))?.id || workflowStages[0].id;

// Keep normalizeBackgroundReaderProfile — uses DEFAULT_BACKGROUND_READER_PROFILE constant
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

export default function App() {
  const { theme, toggleTheme: handleToggleTheme } = useThemePreference(THEME_STORAGE_KEY);
  const { addToast } = useToast();
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

  const { handlePdfUpload } = usePdfUpload({
    apiService,
    createReadyMessages,
    resetArtifacts,
    resetPageNavigation,
    setTaskActive,
    commitTranslationState,
    setPdfFileName,
    setPdfFile,
    setPdfId,
    setDeconstructData,
    setAnalysisData,
    setBackgroundKnowledgeData,
    setBackgroundReaderProfile,
    setMessages,
    setSocraticSession,
    setIsTranslated,
    setActiveTab,
    setPapersList,
    currentPageTextRef,
    showWarning: (msg) => addToast('warning', msg),
    showError: (msg) => addToast('error', msg),
  });



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

  const { handleStartAnalysis } = useCriticalReading({
    apiService,
    pdfId,
    setActiveTab,
    setTaskActive,
    setAnalysisData,
    setPapersList,
    showWarning: (msg) => addToast('warning', msg),
    showError: (msg) => addToast('error', msg),
  });

  const handleGenerateBackgroundKnowledge = useCallback(async (selectedProfile = backgroundReaderProfile, options = {}) => {
    if (!pdfId) {
      addToast('warning', '请先上传 PDF 文件。');
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
        include_library_papers: Boolean(options?.includeLibraryPapers),
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
      addToast('error', error?.response?.data?.message || error?.message || '背景知识图谱生成失败，请稍后重试。');
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

  const {
    handleDeepResearchQuestionChange,
    handleDeepResearchBriefConstraintsChange,
    handlePreviewResearchBrief,
    handleStartResearchTask,
    handleRefreshResearchTask,
    handleReviewResearchPlan,
    handleReviewResearchFinal,
    handleCancelResearchTask,
  } = useDeepResearch({
    apiService,
    pdfId,
    deconstructData,
    deepResearchStateByPdf,
    setDeepResearchStateForPdf,
    fetchDeepResearchTrace,
    currentPdfIdRef,
    setActiveTab,
  });

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

  const {
    handleSendMessage,
    handleAbortChat,
    handleDeleteChatMessage,
    handleExplain,
    handleJumpToSource,
    handleSaveChatToNote,
    handleCaptureChatArtifact,
  } = useChat({
    apiService,
    pdfId,
    messages,
    setMessages,
    setActiveTab,
    deconstructData,
    papersList,
    startChatRequest,
    finishChatRequest,
    abortChatRequest,
    isChatLoading,
    addNote,
    captureArtifact,
    restorePaperState,
    jumpToPage,
    setAppMode,
    setFocusedSourceRequest,
    showWarning: (msg) => addToast('warning', msg),
  });

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
      addToast('error', '重新开始失败，请稍后再试。');
    }
  }, [pdfId]);

  const {
    requestPageTranslation,
    handlePdfPageChange,
    handlePageTextExtracted,
    handleRetryTranslation: handleRetryTranslationFromHook,
  } = usePageTranslation({
    apiService,
    pdfId,
    deconstructData,
    commitTranslationState,
    setPdfPageState,
    pdfPageState,
    isTranslated,
    currentPageTextRef,
  });

  const handleRetryTranslation = useCallback(() => {
    handleRetryTranslationFromHook(translationState);
  }, [handleRetryTranslationFromHook, translationState]);

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
            <ErrorBoundary area="Agent工作区">
            <Suspense fallback={<div className="flex items-center justify-center h-full theme-text-muted">加载 Agent 工作区…</div>}>
              <AgentWorkspace
                paperLibrary={papersList}
                activePaperId={pdfId || ''}
                onCaptureArtifact={handleCaptureWorkbenchArtifact}
                onJumpToSource={handleJumpToSource}
              />
            </Suspense>
            </ErrorBoundary>
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
                    <ErrorBoundary area="PDF阅读区">
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
                    </ErrorBoundary>
                  </Panel>

                  <Separator className="group relative w-1.5 transition-all hover:bg-pixiu/10">
                    <div className="app-separator-line absolute inset-y-0 left-1/2 w-[2px] -translate-x-1/2 transition-colors group-hover:bg-pixiu/40" />
                  </Separator>

                  <Panel defaultSize={42} minSize={32}>
                    <ErrorBoundary area="功能面板区">
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
                    </ErrorBoundary>
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

