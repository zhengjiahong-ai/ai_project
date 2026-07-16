import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart3,
  BookOpen,
  Bookmark,
  FileText,
  Info,
  LayoutDashboard,
  MessageSquare,
  Network,
  Search,
  Sparkles,
} from 'lucide-react';

import {
  createDefaultReaderProfile,
  summarizeReaderProfile,
} from './components/backgroundKnowledgePanelModel.ts';
import CodeExecutionApprovalCenter from './components/CodeExecutionApprovalCenter.jsx';
import LibrarySidebar from './components/LibrarySidebar';
import Navbar from './components/Navbar';
import { ToastProvider, useToast } from './components/Toast.jsx';
import ReadingIDE from './pages/ReadingIDE.jsx';
import AgentResearchPage from './pages/AgentResearchPage.jsx';
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

        <main className="workspace-main flex min-h-0 flex-1 overflow-hidden" aria-label="论文阅读工作区">
          {appMode === 'agent' ? (
            <AgentResearchPage
              papersList={papersList}
              pdfId={pdfId}
              handleCaptureWorkbenchArtifact={handleCaptureWorkbenchArtifact}
              handleJumpToSource={handleJumpToSource}
            />
          ) : (
            <ReadingIDE
              isSidebarCollapsed={isSidebarCollapsed}
              setIsSidebarCollapsed={setIsSidebarCollapsed}
              pdfFile={pdfFile}
              pdfFileName={pdfFileName}
              pdfPageState={pdfPageState}
              currentPaperStatus={currentPaperStatus}
              readingProgress={readingProgress}
              notes={notes}
              papersList={papersList}
              handleSelectPaper={handleSelectPaper}
              setIsLibraryOpen={setIsLibraryOpen}
              outlineQuery={outlineQuery}
              setOutlineQuery={setOutlineQuery}
              currentOutlineItem={currentOutlineItem}
              paperOutlineModel={paperOutlineModel}
              collapsedOutlineIds={collapsedOutlineIds}
              visibleOutlineItems={visibleOutlineItems}
              toggleOutlineCollapse={toggleOutlineCollapse}
              handleSelectOutlineItem={handleSelectOutlineItem}
              isDeconstructing={isDeconstructing}
              deconstructData={deconstructData}
              setActiveTab={setActiveTab}
              theme={theme}
              handleExplain={handleExplain}
              addNote={addNote}
              pdfHighlights={pdfHighlights}
              handleHighlightsChange={handleHighlightsChange}
              handlePdfPageChange={handlePdfPageChange}
              handlePageTextExtracted={handlePageTextExtracted}
              targetPageIndex={targetPageIndex}
              targetPageJumpToken={targetPageJumpToken}
              focusedSourceRequest={focusedSourceRequest}
              pdfId={pdfId}
              isTranslated={isTranslated}
              activeTab={activeTab}
              activeTabMeta={activeTabMeta}
              ActiveTabIcon={ActiveTabIcon}
              activeWorkspaceSection={activeWorkspaceSection}
              visibleWorkspaceTabs={visibleWorkspaceTabs}
              workspaceTabsRef={workspaceTabsRef}
              handleWorkspaceTabsWheel={handleWorkspaceTabsWheel}
              currentWorkflowStage={currentWorkflowStage}
              workflowStepSummary={workflowStepSummary}
              setActiveWorkspaceSectionId={setActiveWorkspaceSectionId}
              setIsWorkspaceNavExpanded={setIsWorkspaceNavExpanded}
              isWorkspaceNavExpanded={isWorkspaceNavExpanded}
              readingContext={readingContext}
              backgroundReaderProfile={backgroundReaderProfile}
              setBackgroundReaderProfile={setBackgroundReaderProfile}
              backgroundReaderProfileSummary={backgroundReaderProfileSummary}
              primaryNextActionSuggestion={primaryNextActionSuggestion}
              nextActionSuggestions={nextActionSuggestions}
              handleReadingWorkflowAction={handleReadingWorkflowAction}
              messages={messages}
              handleSendMessage={handleSendMessage}
              handleDeleteChatMessage={handleDeleteChatMessage}
              handleSaveChatToNote={handleSaveChatToNote}
              handleCaptureChatArtifact={handleCaptureChatArtifact}
              handleJumpToSource={handleJumpToSource}
              handleAbortChat={handleAbortChat}
              isChatLoading={isChatLoading}
              isSocraticLoading={isSocraticLoading}
              socraticSession={socraticSession}
              handleReadingProgressChange={handleReadingProgressChange}
              handleStartSocratic={handleStartSocratic}
              handleSubmitSocraticAnswer={handleSubmitSocraticAnswer}
              handleRestartSocratic={handleRestartSocratic}
              backgroundKnowledgeData={backgroundKnowledgeData}
              isBackgroundKnowledgeLoading={isBackgroundKnowledgeLoading}
              handleGenerateBackgroundKnowledge={handleGenerateBackgroundKnowledge}
              handleCaptureWorkbenchArtifact={handleCaptureWorkbenchArtifact}
              currentDeepResearchState={currentDeepResearchState}
              currentResearchProgress={currentResearchProgress}
              handleDeepResearchQuestionChange={handleDeepResearchQuestionChange}
              handleStartResearchTask={handleStartResearchTask}
              handlePreviewResearchBrief={handlePreviewResearchBrief}
              handleDeepResearchBriefConstraintsChange={handleDeepResearchBriefConstraintsChange}
              setDeepResearchStateForPdf={setDeepResearchStateForPdf}
              handleRefreshResearchTask={handleRefreshResearchTask}
              handleCancelResearchTask={handleCancelResearchTask}
              handleReviewResearchPlan={handleReviewResearchPlan}
              handleReviewResearchFinal={handleReviewResearchFinal}
              fetchDeepResearchTrace={fetchDeepResearchTrace}
              paperOutlineItems={paperOutlineItems}
              analysisData={analysisData}
              handleStartAnalysis={handleStartAnalysis}
              isAnalyzing={isAnalyzing}
              translationState={translationState}
              currentTranslationPage={currentTranslationPage}
              handleRetryTranslation={handleRetryTranslation}
              apiService={apiService}
              workbenchCards={workbenchCards}
              setIsWorkbenchCollapsed={setIsWorkbenchCollapsed}
              workbenchPanelRef={workbenchPanelRef}
              isWorkbenchCollapsed={isWorkbenchCollapsed}
              handleToggleWorkbenchCollapsed={handleToggleWorkbenchCollapsed}
              removeArtifact={removeArtifact}
              toggleArtifactPinned={toggleArtifactPinned}
              updateArtifact={updateArtifact}
              handleCaptureNoteToWorkbench={handleCaptureNoteToWorkbench}
              handleSaveArtifactAsNote={handleSaveArtifactAsNote}
              handleDeleteNote={handleDeleteNote}
            />
          )}
        </main>
      </div>
    </>
  );
}

