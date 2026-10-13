import React, { useCallback, useEffect, useEffectEvent, useLayoutEffect, useMemo, useRef, useState } from 'react';
import TaskSwitcher from './components/TaskSwitcher';
import WorkbenchPopover from './components/WorkbenchPopover';
import useCompactLayout from './hooks/useCompactLayout';
import useWorkbenchWidth from './hooks/useWorkbenchWidth';
import { clamp, DEFAULT_WORKBENCH_LAYOUT, workbenchLayout } from './utils/workbenchLayout';
import PaperPageNavigation from './components/PaperPageNavigation';
import { selectionNote } from './utils/selectionNote';
import { materialDraft } from './utils/materialMentions';
import { BookOpen, ChevronLeft, ChevronRight, FilePlus2, Languages, MessageSquare, Moon, PanelLeftClose, PanelLeftOpen, PanelRightOpen, Save, Sun, Upload } from 'lucide-react';
import ChatPanel from './components/ChatPanel';
import MarkdownContent from './components/MarkdownContent';
import CritiqueContent from './components/CritiqueContent';
import { critiqueVersion, critiqueMessageIsCurrent, resolveCritiqueFollowup } from './utils/critiqueFollowup';
import { locatePdfQuote } from './utils/pdfQuoteLocator';
import PdfViewer from './components/PdfViewer';
import TaskNavigation from './components/TaskNavigation';
import DocumentActions from './components/DocumentActions';
import DocumentTitle from './components/DocumentTitle';
import CollapsedSources from './components/CollapsedSources';
import DocumentOriginalPage from './components/DocumentOriginalPage';
import { documentOriginalPage } from './utils/documentOriginalPage';
import { documentSources } from './utils/documentSources';
import { documentMarkdownExport } from './utils/documentExport';
import { documentDisplayTitle, questionTopic } from './utils/documentPresentation';
import { learningActivityHistory } from './utils/learningActivityHistory';
import { reviseDocument, documentText } from './utils/documentVersions';
import TaskDraftRecovery from './components/TaskDraftRecovery';
import TranslationPanel from './components/TranslationPanel';
import { useTaskWorkspace } from './hooks/useTaskWorkspace';
import { useTaskLearning } from './hooks/useTaskLearning';
import { useTaskResearch } from './hooks/useTaskResearch';
import { ResearchCard } from './components/ConversationResearch';
import { sanitizeResearchReport } from './components/deepResearchPanelModel';
import { getResearchStatusMeta } from './components/deepResearchPanelModel';
import { OperationRecord } from './components/ConversationExecution';
import { operationStatusText } from './components/conversationProcessingModel';
import TaskProcessingHistory from './components/TaskProcessingHistory';
import { LearningRecordContent } from './components/LearningHistory';
import { conversationTimeline, documentMessageIndex } from './utils/conversationTimeline';
import { useThemePreference } from './hooks/useThemePreference';
import { apiService } from './services/api';
import { initDB } from './services/localDb';
import { persistTranslationState } from './services/workspaceSession';
import { taskWorkspaceApi } from './services/taskWorkspaceApi';
import { taskResearchApi } from './services/taskResearchApi';
import { getResearchIntent, clearResearchIntent } from './services/researchStartIntent';
import { loadTaskMaterial } from './services/taskMaterialCache';
import { taskWorkspaceRemoteStore } from './services/taskWorkspaceRemoteStore';
import { buildPaperOutlineModel } from './utils/appHelpers';
import { resolveConversationIntent, startsNewCapability } from './utils/conversationSkills';
import { resolveTaskContext } from './utils/taskWorkspaceModel';
import { resolveNamedTaskPapers } from './utils/namedTaskPapers';
import { createEmptyTranslationState, normalizeTranslationState } from './utils/translationState';
import { usePageTranslation } from './hooks/usePageTranslation';
import './UnifiedTaskApp.css';
import './WorkbenchTheme.css';

const LAYOUT_KEY = 'pixiu-unified-layout-v1';
const COMPACT_PANE_KEY = 'pixiu-compact-pane-v1';
const DEFAULT_LAYOUT = DEFAULT_WORKBENCH_LAYOUT;
const activityPriority = status => {
  if (['running', 'cancelling', 'stopping'].includes(status)) return 0;
  if (status === 'queued') return 1;
  if (['waiting_user', 'awaiting_submission', 'active'].includes(status)) return 2;
  return 3;
};
const initialLayout = () => {
  try {
    const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || '{}');
    const merged = { ...DEFAULT_LAYOUT, ...saved };
    merged.reader = Boolean(merged.reader);
    merged.chat = Boolean(merged.chat);
    if (!merged.reader && !merged.chat) merged.reader = true;
    merged.readerPercent = Number.isFinite(Number(merged.readerPercent)) ? Math.max(32, Math.min(72, Number(merged.readerPercent))) : DEFAULT_LAYOUT.readerPercent;
    merged.navWidth = Number.isFinite(Number(merged.navWidth)) ? clamp(Number(merged.navWidth), 200, 320) : DEFAULT_LAYOUT.navWidth;
    merged.navPinnedMedium = merged.navPinnedMedium === true;
    return merged;
  } catch { return DEFAULT_LAYOUT; }
};
const makeId = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
const createMessage = (role, content, extra = {}) => ({ id: makeId(), role, content, timestamp: Date.now(), ...extra });
const getPaperTitle = (papers, id) => papers.find((paper) => paper.id === id)?.title || papers.find((paper) => paper.id === id)?.filename || id;
const normalizeNoteContent = (note) => `${note?.text ?? note?.content ?? note?.body ?? ''}`;
const documentDraftKey = (selection) => `pixiu-document-draft:${JSON.stringify([selection.taskId, selection.collection, selection.id ?? selection.index])}`;
const readingPositionKey = (taskId, paperId) => `pixiu-reading-position:${JSON.stringify([taskId, paperId])}`;
const contentViewKey = taskId => `pixiu-content-view:${taskId}`;
const contentReturnKey = taskId => `pixiu-content-return:${taskId}`;
const storeView = (taskId, value, keepReturn = false) => {
  try {
    localStorage.setItem(contentViewKey(taskId), JSON.stringify(value));
    if (keepReturn) localStorage.setItem(contentReturnKey(taskId), JSON.stringify(value));
  } catch { /* The saved task remains available if local preferences are disabled. */ }
};
const shortPaperTitle = (papers, id) => getPaperTitle(papers, id).split(/[:：]/u)[0].slice(0, 56);
export default function UnifiedTaskApp() {
  const workspace = useTaskWorkspace();
  const learning = useTaskLearning(workspace);
  const research = useTaskResearch(workspace, undefined, learning.operations);
  const { tasks, activeTask, activeTaskId, createTask, updateTask, selectTask } = workspace;
  const savedLearningActivities = learningActivityHistory(activeTask);
  const { theme, toggleTheme } = useThemePreference('pixiu-theme');
  const [layout, setLayout] = useState(initialLayout);
  const compact = useCompactLayout();
  const width = useWorkbenchWidth();
  const viewLayout = workbenchLayout(layout, width, compact);
  const [compactPane, setCompactPane] = useState(() => {
    try { return localStorage.getItem(COMPACT_PANE_KEY) === 'reader' ? 'reader' : 'chat'; }
    catch { return 'chat'; }
  });
  const [compactNavigation, setCompactNavigation] = useState(false);
  const drawerOpen = viewLayout.drawer && compactNavigation;
  const compactNavigationButton = useRef(null);
  const compactReaderButton = useRef(null);
  const navigationRef = useRef(null);
  const resizeCleanup = useRef(null);
  const patchLayout = useCallback((patch) => {
    if (patch.reader === true && patch.chat !== true) { setCompactPane('reader'); setCompactNavigation(false); if (compact) compactReaderButton.current?.focus(); }
    if (patch.chat === true && patch.reader !== true) { setCompactPane('chat'); setCompactNavigation(false); }
    setLayout((current) => {
      const next = { ...current, ...patch };
      if (!next.reader && !next.chat) next.reader = true;
      next.mode = next.reader && next.chat ? 'split' : next.reader ? 'reader' : 'chat';
      return next;
    });
  }, [compact]);
  useEffect(() => () => resizeCleanup.current?.(), []);
  useEffect(() => {
    if (drawerOpen) navigationRef.current?.querySelector('select, button, input')?.focus();
  }, [drawerOpen]);
  useEffect(() => { if (!viewLayout.drawer) setCompactNavigation(false); }, [viewLayout.drawer]);
  useEffect(() => {
    if (!compact) return;
    try { localStorage.setItem(COMPACT_PANE_KEY, compactPane); } catch { /* Layout preference is optional. */ }
  }, [compact, compactPane]);
  const [papers, setPapers] = useState([]);
  const [libraryError, setLibraryError] = useState('');
  const [uploading, setUploading] = useState(false);
  const uploadController = useRef(null);
  useEffect(() => () => uploadController.current?.abort(), []);
  const [processingRefresh, setProcessingRefresh] = useState(0);
  const [processingRequest, setProcessingRequest] = useState(false);
  const [paperView, setPaperView] = useState({ id: null, url: null, deconstruct: null, highlights: [], error: '' });
  const [page, setPage] = useState({ pageIndex: 0, totalPages: 0 });
  const [jump, setJump] = useState({ pageIndex: 0, token: 0, anchorId: null });
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [selectedLearning, setSelectedLearning] = useState(null);
  const selectedLearningRef = useRef(null);
  selectedLearningRef.current = selectedLearning;
  const [returnContent, setReturnContent] = useState(null);
  const restoredContentTask = useRef(null);
  const contentScrollRef = useRef(null);
  const [showProcessingHistory, setShowProcessingHistory] = useState(false);
  const processingDialogRef = useRef(null);
  useEffect(() => {
    if (!showProcessingHistory) return;
    const previous = document.activeElement;
    const returnFocus = previous?.closest('.workbench-popover')?.querySelector('.workbench-popover-trigger') || previous;
    const dialog = processingDialogRef.current;
    const background = [...(dialog?.closest('.unified-app')?.children || [])].filter(node => node.matches('header, main'));
    background.forEach(node => node.setAttribute('inert', ''));
    dialog?.querySelector('button')?.focus();
    return () => { background.forEach(node => node.removeAttribute('inert')); if (returnFocus?.isConnected) returnFocus.focus(); };
  }, [showProcessingHistory]);
  const [focusMessage, setFocusMessage] = useState(null);
  const [composerError, setComposerError] = useState('');
  const [composerDraft, setComposerDraft] = useState('');
  const [critiqueSelection, setCritiqueSelection] = useState(null);
  const [critiqueTargetChoice, setCritiqueTargetChoice] = useState(null);
  const selectCritiqueIssue = (artifactId, issueId, message) => {
    const artifact = activeTask?.artifacts?.find(item => (item.id || item.artifactId) === artifactId);
    if (!artifact || !critiqueVersion(artifact)) return;
    if (!critiqueMessageIsCurrent(artifact, message)) {
      setComposerError('这条回答对应旧版本，请打开成果查看当前判断，或在历史版本中找回原记录。');
      return;
    }
    setCritiqueSelection({ taskId: activeTaskId, title: artifact.title, followup: {
      artifactId, issueId, version: critiqueVersion(artifact),
    } });
    learning.setInputMode('chat');
    setCompactPane('chat');
  };
  const prepareCritiqueRegeneration = artifact => {
    setCritiqueSelection({ taskId: activeTaskId, title: artifact.title, followup: {
      artifactId: artifact.id || artifact.artifactId, version: critiqueVersion(artifact), regenerate: true,
    } });
    setComposerDraft(`/批判 ${artifact.critique.question?.original || '整体批判阅读这篇论文'}`);
    learning.setInputMode('chat');
    setCompactPane('chat');
  };
  const [materialError, setMaterialError] = useState('');
  const [movingDocument, setMovingDocument] = useState(false);
  const [requestedDocument, setRequestedDocument] = useState(null);
  const [recoveryPreview, setRecoveryPreview] = useState(null);
  const [savingRecovery, setSavingRecovery] = useState(false);
  const activeTaskIdRef = useRef(activeTaskId);
  activeTaskIdRef.current = activeTaskId;
  const [documentDraft, setDocumentDraft] = useState('');
  const [restoringDocument, setRestoringDocument] = useState(false);
  const [documentEditing, setDocumentEditing] = useState(false);
  const [savingDocument, setSavingDocument] = useState(false);
  const selectedDocumentRef = useRef(null);
  selectedDocumentRef.current = selectedDocument;
  const recoveryPreviewRef = useRef(null);
  recoveryPreviewRef.current = recoveryPreview;
  const [localError, setLocalError] = useState('');
  const [intentChoice, setIntentChoice] = useState(null);
  const [showOutline, setShowOutline] = useState(false);
  const [translationMode, setTranslationMode] = useState('original');
  const [researchCapabilities, setResearchCapabilities] = useState(null);
  const [researchSettings, setResearchSettings] = useState({});
  const researchSourcePolicy = researchSettings[activeTaskId]?.sourcePolicy || 'task_only';
  const researchBudgetProfile = researchSettings[activeTaskId]?.budgetProfile || 'standard';
  const researchContextRefs = researchSettings[activeTaskId]?.contextRefs || [];
  const setResearchContextRefs = contextRefs => setResearchSettings(current => ({ ...current,
    [activeTaskId]: { ...current[activeTaskId], contextRefs } }));
  const setResearchSourcePolicy = sourcePolicy => setResearchSettings(current => ({ ...current,
    [activeTaskId]: { ...current[activeTaskId], sourcePolicy } }));
  const setResearchBudgetProfile = budgetProfile => setResearchSettings(current => ({ ...current,
    [activeTaskId]: { ...current[activeTaskId], budgetProfile } }));
  const sourceAddIntents = useRef(new Map());
  const readerRef = useRef(null);
  const [readerWidth, setReaderWidth] = useState(0);
  const [narrowTranslationSide, setNarrowTranslationSide] = useState('original');
  useEffect(() => {
    const element = readerRef.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => setReaderWidth(element.clientWidth));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const narrowParallel = translationMode === 'parallel' && readerWidth > 0 && readerWidth < 900;
  const displayedTranslationMode = narrowParallel ? narrowTranslationSide : translationMode;
  const [translationState, setTranslationState] = useState(createEmptyTranslationState());
  const [translationReadyKey, setTranslationReadyKey] = useState('');
  const currentPageTextRef = useRef({ pageIndex: 0, pageText: '', pageLayout: null });
  const fileInputRef = useRef(null);
  const taskRef = useRef(new Map());
  const paperLoadToken = useRef(0);
  const materialProcessingRef = useRef(new Map());
  const focusedPaperId = activeTask?.focusedPaperId || null;
  const focusedMetadataKey = JSON.stringify(papers.find(paper => paper.id === focusedPaperId)?.externalSource || null);
  useEffect(() => {
    try { setShowOutline(localStorage.getItem(`pixiu-outline:${JSON.stringify([activeTaskId, focusedPaperId])}`) === 'open'); }
    catch { setShowOutline(false); }
  }, [activeTaskId, focusedPaperId]);
  const toggleOutline = () => {
    const next = !showOutline;
    setShowOutline(next);
    try { localStorage.setItem(`pixiu-outline:${JSON.stringify([activeTaskId, focusedPaperId])}`, next ? 'open' : 'closed'); }
    catch { /* The in-page directory remains usable without preferences. */ }
  };
  const translationKey = JSON.stringify([activeTaskId, focusedPaperId]);
  const translationReady = translationReadyKey === translationKey;
  const initialPaperPage = useMemo(() => {
    try {
      const stored = Number(localStorage.getItem(readingPositionKey(activeTaskId, focusedPaperId)));
      return Number.isInteger(stored) && stored >= 0 ? stored : 0;
    } catch { return 0; }
  }, [activeTaskId, focusedPaperId]);
  const setReadingPage = useCallback(next => {
    // Hidden PDF layout observers must not overwrite the last visible position.
    if (selectedDocumentRef.current || selectedLearningRef.current || recoveryPreviewRef.current) return;
    setPage(next);
    if (activeTaskId && focusedPaperId) {
      try { localStorage.setItem(readingPositionKey(activeTaskId, focusedPaperId), String(next.pageIndex)); }
      catch { /* Reading position is an optional local preference. */ }
    }
  }, [activeTaskId, focusedPaperId]);
  const materialKey = JSON.stringify([activeTaskId, activeTask?.paperIds || []]);

  useEffect(() => {
    const [taskId, ids] = JSON.parse(materialKey);
    if (!taskId || !taskWorkspaceApi.getMaterialProcessing) return;
    let disposed = false;
    let timer;
    const poll = async () => {
      try {
        const results = await Promise.allSettled(ids.map(id => taskWorkspaceApi.getMaterialProcessing(taskId, id)));
        if (disposed) return;
        let pending = false;
        let retryDelay = 2500;
        const db = await initDB();
        for (const result of results) {
          if (result.status !== 'fulfilled') {
            // Missing legacy files cannot become available through polling.
            // Retry only transient failures, leaving an explicit refresh as
            // the recovery path after restoring a file.
            if ([400, 404].includes(result.reason?.response?.status)) continue;
            pending = true;
            if (result.reason?.response?.status === 429) retryDelay = Math.max(retryDelay, 15000,
              Number(result.reason.response.data?.retryAfter || 0) * 1000);
            continue;
          }
          const status = result.value;
          if (!ids.includes(status?.pdfId)) continue;
          materialProcessingRef.current.set(status.pdfId, status);
          pending ||= ['queued', 'parsing'].includes(status.processingStatus) || status.aiAnalysisStatus === 'running';
          await db.put('deconstructStore', status, status.pdfId);
          if (disposed) return;
          setPapers(current => current.map(paper => paper.id === status.pdfId ? { ...paper, ...status, id: paper.id } : paper));
          setPaperView(current => current.id === status.pdfId ? { ...current, deconstruct: status } : current);
        }
        if (pending && !disposed) timer = setTimeout(poll, retryDelay);
      } catch { if (!disposed) timer = setTimeout(poll, 5000); }
    };
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [materialKey, processingRefresh]);

  const requestMaterialProcessing = async (overview) => {
    if (!activeTaskId || !focusedPaperId || processingRequest) return;
    setProcessingRequest(true);
    try {
      if (overview) await taskWorkspaceApi.generateMaterialOverview(activeTaskId, focusedPaperId);
      else await taskWorkspaceApi.retryMaterialParse(activeTaskId, focusedPaperId);
      setProcessingRefresh(value => value + 1);
    } catch (error) { setMaterialError(error.response?.data?.message || error.message || '处理请求失败'); }
    finally { setProcessingRequest(false); }
  };

  const { requestPageTranslation, handlePdfPageChange, handlePageTextExtracted, handleRetryTranslation, handleCancelTranslation } = usePageTranslation({
    apiService,
    pdfId: focusedPaperId,
    deconstructData: paperView.deconstruct,
    translationState,
    commitTranslationState: setTranslationState,
    setPdfPageState: setReadingPage,
    pdfPageState: page,
    isTranslated: translationReady && translationMode !== 'original',
    currentPageTextRef,
  });
  useEffect(() => {
    if (!translationReady || translationMode === 'original' || !focusedPaperId || paperView.id !== focusedPaperId) return;
    const source = currentPageTextRef.current;
    if (!source.pageText || source.pageIndex !== page.pageIndex) return;
    const status = translationState.pages?.[page.pageIndex]?.status;
    if (['success', 'partial', 'translating', 'cancelled', 'error', 'empty'].includes(status)) return;
    void requestPageTranslation(source);
  }, [translationReady, translationMode, focusedPaperId, paperView.id, page.pageIndex, translationState.pages, requestPageTranslation]);

  useEffect(() => { taskRef.current = new Map(tasks.map((task) => [task.id, task])); }, [tasks]);
  useEffect(() => { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)); }, [layout]);
  useEffect(() => {
    setSelectedDocument(null); setSelectedLearning(null); setRecoveryPreview(null); setDocumentDraft('');
    setLocalError(''); setComposerError(''); setMaterialError(''); setShowProcessingHistory(false);
    setReturnContent(null); setFocusMessage(null);
  }, [activeTaskId]);
  useEffect(() => {
    if (!requestedDocument || requestedDocument.taskId !== activeTaskId) return;
    const collection = activeTask?.artifacts?.some(document => (document.id || document.artifactId) === requestedDocument.id) ? 'artifacts' : 'notes';
    const item = activeTask?.[collection]?.find(document => (document.id || document.artifactId) === requestedDocument.id);
    if (!item) { setLocalError('成果已再次移动，请刷新任务列表'); setRequestedDocument(null); return; }
    let draft = null;
    const selection = { taskId: activeTaskId, collection, id: requestedDocument.id, baseText: normalizeNoteContent(item) };
    try {
      const key = documentDraftKey(selection);
      draft = localStorage.getItem(key);
      if (draft !== null) selection.baseText = JSON.parse(localStorage.getItem(key + ':base') || 'null');
    } catch { setLocalError('本地编辑草稿暂不可用'); }
    setSelectedLearning(null); setRecoveryPreview(null);
    setSelectedDocument(selection); setDocumentDraft(draft ?? normalizeNoteContent(item));
    const view = { kind: 'document', collection, id: requestedDocument.id };
    storeView(activeTaskId, view, true); setReturnContent(view);
    setRequestedDocument(null); patchLayout({ reader: true });
  }, [activeTaskId, activeTask, requestedDocument, patchLayout]);
  useEffect(() => {
    let alive = true;
    initDB().then((db) => db.getAll('libraryStore')).then((records) => {
      if (alive) setPapers(records.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0)));
    }).catch((error) => { if (alive) setLibraryError(error.message || '论文资料读取失败'); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    let disposed = false;
    const [taskId] = JSON.parse(materialKey);
    if (taskId) taskWorkspaceApi.listMaterials(taskId).then(items => {
      if (disposed) return;
      setLibraryError('');
      setPapers(current => {
        const known = new Map(current.map(item => [item.id, item]));
        for (const item of items) known.set(item.id, { ...known.get(item.id), ...item });
        return [...known.values()];
      });
    }).catch(error => { if (!disposed) setLibraryError(error.message || '任务论文读取失败'); });
    return () => { disposed = true; };
  }, [materialKey]);

  useEffect(() => {
    if (!activeTaskId) { setResearchCapabilities(null); return; }
    setResearchCapabilities(null);
    let disposed = false;
    taskResearchApi.capabilities(activeTaskId).then(response => {
      if (!disposed) setResearchCapabilities(response?.data || response || null);
    }).catch(() => { if (!disposed) setResearchCapabilities(null); });
    return () => { disposed = true; };
  }, [activeTaskId]);

  useEffect(() => {
    let alive = true;
    currentPageTextRef.current = { pageIndex: initialPaperPage, pageText: '', pageLayout: null };
    setPage({ pageIndex: initialPaperPage, totalPages: 0 });
    setTranslationMode('original');
    setTranslationReadyKey('');
    setTranslationState(createEmptyTranslationState(focusedPaperId, {currentPage:initialPaperPage}));
    if (focusedPaperId) initDB().then((db) => db.get('translationStore', focusedPaperId)).then((stored) => {
      if (!alive) return;
      const restored = normalizeTranslationState(stored, focusedPaperId);
      setTranslationState(current => ({...restored,
        currentPage:current.pdfId === focusedPaperId ? current.currentPage : initialPaperPage,
        pages:{
        ...(current.pdfId === focusedPaperId ? current.pages : {}), ...restored.pages,
      }}));
      setTranslationReadyKey(translationKey);
    }).catch(() => { if (alive) setLocalError('译文缓存读取失败，请刷新后重试。'); });
    return () => { alive = false; };
  }, [focusedPaperId, activeTaskId, initialPaperPage, translationKey]);
  useEffect(() => {
    if (!translationReady || !focusedPaperId || translationState.pdfId !== focusedPaperId) return;
    const timer = setTimeout(() => {
      initDB().then((db) => persistTranslationState(db, focusedPaperId, translationState)).catch((error) => setLocalError(error.message || '译文缓存保存失败'));
    }, 300);
    return () => clearTimeout(timer);
  }, [translationReady, focusedPaperId, translationState]);
  useEffect(() => {
    const token = ++paperLoadToken.current;
    let objectUrl = null;
    if (!focusedPaperId) { setPaperView({ id: null, url: null, deconstruct: null, highlights: [], error: '' }); return undefined; }
    setPaperView({ id: focusedPaperId, url: null, deconstruct: null, highlights: [], error: '' });
    const selectedPaper = papers.find(paper => paper.id === focusedPaperId);
    if (selectedPaper?.fileUnavailable === 'metadata_only') {
      setPaperView({ id: focusedPaperId, url: null, deconstruct: null, highlights: [], error: '', metadata: selectedPaper.externalSource || selectedPaper });
      return undefined;
    }
    initDB().then(async (db) => {
      const { record, deconstruct, highlights, cacheWarning } = await loadTaskMaterial(db, taskWorkspaceApi, activeTaskId, focusedPaperId);
      if (cacheWarning && token === paperLoadToken.current) setLocalError(cacheWarning);
      objectUrl = URL.createObjectURL(record.blob);
      if (token === paperLoadToken.current) setPaperView({ id: focusedPaperId, url: objectUrl, deconstruct: materialProcessingRef.current.get(focusedPaperId) || deconstruct, highlights: Array.isArray(highlights) ? highlights : [], error: '' });
      else URL.revokeObjectURL(objectUrl);
    }).catch((error) => { if (token === paperLoadToken.current) setPaperView({ id: focusedPaperId, url: null, deconstruct: null, highlights: [],
      error: error.response?.data?.message || (error.response?.status === 404 ? '这篇论文暂不可读取，请检查任务材料或恢复文件。原笔记与成果仍保留。'
        : error.message || '论文读取失败') }); });
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [focusedPaperId, activeTaskId, focusedMetadataKey]);

  const setMode = (mode) => {
    if (mode !== 'split') setCompactPane(mode);
    patchLayout(mode === 'reader' ? { mode, reader: true, chat: false }
      : mode === 'chat' ? { mode, reader: false, chat: true } : { mode: 'split', reader: true, chat: true });
  };
  const openPaper = useCallback(async (paperId, taskId = activeTaskId) => {
    const task = taskRef.current.get(taskId);
    if (!task?.paperIds.includes(paperId)) throw new Error('这篇论文不属于当前任务');
    setJump({ pageIndex: 0, token: 0, anchorId: null });
    setSelectedDocument(null);
    setSelectedLearning(null);
    setRecoveryPreview(null);
    setReturnContent(null);
    storeView(taskId, { kind: 'paper' });
    patchLayout({ reader: true });
    await updateTask(taskId, { focusedPaperId: paperId });
  }, [activeTaskId, updateTask, patchLayout]);
  const addPaper = async (paperId) => {
    if (!activeTaskId) return;
    await updateTask(activeTaskId, (task) => ({ paperIds: [...new Set([...task.paperIds, paperId])], focusedPaperId: task.focusedPaperId || paperId }));
  };
  const removePaper = async (paperId) => {
    if (!activeTaskId) return;
    await updateTask(activeTaskId, (task) => {
      const paperIds = task.paperIds.filter((id) => id !== paperId);
      return { paperIds, focusedPaperId: task.focusedPaperId === paperId ? paperIds[0] || null : task.focusedPaperId };
    });
  };
  const handleUpload = async (file) => {
    if (!file || uploadController.current) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) { setMaterialError('请选择 PDF 论文文件。'); return; }
    const controller = new AbortController();
    uploadController.current = controller;
    let targetTaskId = activeTaskId;
    setUploading(true); setMaterialError('');
    try {
      targetTaskId = activeTaskId || (await createTask({ title: file.name.replace(/\.pdf$/i, '') })).id;
      if (controller.signal.aborted) return;
      const response = await apiService.uploadTaskMaterial(file, controller.signal);
      if (controller.signal.aborted) return;
      if (!response || response.status !== 'success' || !response.pdfId) throw new Error(response?.message || '论文上传失败');
      const entry = { ...response, id: response.pdfId, title: response.title || file.name, filename: file.name, authors: response.authors || [], parseStatus: response.parseStatus || '已上传', ragIndexed: response.ragIndexed === true, timestamp: Date.now(), updatedAt: Date.now() };
      const db = await initDB();
      // Reimporting a paper must not reset its legacy notes, history or highlights.
      const transaction = db.transaction(['pdfStore', 'deconstructStore', 'libraryStore'], 'readwrite');
      await Promise.all([
        transaction.objectStore('pdfStore').put(file, response.pdfId),
        transaction.objectStore('deconstructStore').put(response, response.pdfId),
        transaction.objectStore('libraryStore').put(entry),
      ]);
      await transaction.done;
      setPapers((current) => [entry, ...current.filter((paper) => paper.id !== entry.id)]);
      if (controller.signal.aborted) return;
      await updateTask(targetTaskId, (task) => ({ paperIds: [...new Set([...task.paperIds, entry.id])], focusedPaperId: entry.id }));
      if (!activeTaskIdRef.current || activeTaskIdRef.current === targetTaskId) {
        selectTask(targetTaskId); patchLayout({ reader: true });
      }
    } catch (error) { if (!controller.signal.aborted && activeTaskIdRef.current === targetTaskId) setMaterialError(error?.response?.data?.message || '论文上传未完成，请重新选择文件再试；当前任务和输入草稿仍保留。'); }
    finally { if (uploadController.current === controller) { uploadController.current = null; setUploading(false); if (fileInputRef.current) fileInputRef.current.value = ''; } }
  };
  const cancelUpload = () => {
    uploadController.current?.abort();
    // The server may already have stored the file. Cancellation stops waiting and
    // automatic association; it never claims to delete a server-side material.
    uploadController.current = null; setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const appendMessage = (taskId, message) => updateTask(taskId, (task) => ({ messages: [...task.messages, message] }));
  const sendMessage = async (rawText, chosenSkill = null, chosenTargets = null) => {
    const task = activeTask;
    if (!task || learning.busyTasks[task.id]) return false;
    const inputError = message => { if (activeTaskIdRef.current === task.id) setComposerError(message); };
    const text = rawText.trim();
    if (!text) return false;
    const followup = resolveCritiqueFollowup(task, text, critiqueSelection);
    if (followup?.error) { inputError(followup.error); return false; }
    setComposerError('');
    const intent = chosenSkill ? { skill: chosenSkill } : resolveConversationIntent(text);
    const skill = intent.skill;
    if (intent.clarification) {
      setIntentChoice({ taskId: task.id, text, ...intent.clarification });
      return false;
    }
    setIntentChoice(null);
    if (text.startsWith('/') && !skill) {
      setComposerError('未识别这个命令，可使用 /精读、/补课、/自测、/批判、/比较、/研究。');
      return false;
    }
    let explicitPaperIds;
    let initialContext;
    try {
      explicitPaperIds = resolveNamedTaskPapers(text, papers, task.paperIds);
      initialContext = resolveTaskContext(task, { text,
        ...((skill && startsNewCapability(skill.skillId)) || learning.inputMode === 'chat' ? { activity: null } : {}),
        ...(explicitPaperIds !== undefined ? { paperIds: explicitPaperIds } : {}) });
    } catch (error) { setComposerError(error.message); return false; }
    const materialReady = (ids) => {
      const notReady = ids.filter(id => papers.find(paper => paper.id === id)?.questionReady === false);
      if (!notReady.length) return true;
      setComposerError(`以下材料正文尚未就绪：${notReady.map(id => getPaperTitle(papers, id)).join('、')}。可先阅读原文，或在论文栏重试解析。`);
      return false;
    };
    const activityPapers = task.activeActivity?.snapshot?.paperIds || task.activeActivity?.paperIds || (task.activeActivity?.pdfId ? [task.activeActivity.pdfId] : []);
    const targetsCurrentActivity = initialContext.allowedPaperIds.length > 0
      && initialContext.allowedPaperIds.every(id => activityPapers.includes(id))
      && activityPapers.every(id => initialContext.allowedPaperIds.includes(id));
    const sendText = skill ? skill.instruction : text;
    if (skill && ['read', 'quiz'].includes(skill.skillId)) {
      try {
        const explicit = explicitPaperIds;
        const pdfId = explicit?.length === 1 ? explicit[0] : !explicit ? task.focusedPaperId || (task.paperIds.length === 1 ? task.paperIds[0] : null) : null;
        if (!pdfId) throw new Error('请打开或明确指定一篇要学习的论文');
        if (!materialReady([pdfId])) return false;
        await learning.start(task, pdfId, skill.skillId, sendText);
      } catch (error) { inputError(error.message); return false; }
      return;
    }
    if (!followup && !skill && learning.inputMode !== 'chat' && task.activeActivity?.status === 'active' && targetsCurrentActivity) {
      if (!materialReady(initialContext.allowedPaperIds)) return false;
      await learning.act(task, learning.inputMode, text);
      return;
    }
    if (skill?.skillId === 'background' && task.activeActivity?.status === 'active' && targetsCurrentActivity) {
      if (!materialReady(initialContext.allowedPaperIds)) return false;
      await learning.act(task, 'remediate', sendText);
      return;
    }
    if (skill && startsNewCapability(skill.skillId)) learning.setInputMode('chat');
    if (skill?.skillId === 'research') {
      try {
        if (!sendText) throw new Error('请在 /研究 后写下要研究的问题');
        const scope = resolveTaskContext(task, { text, activity: null, paperIds: resolveNamedTaskPapers(text, papers, task.paperIds) });
        const v2 = researchCapabilities ? researchCapabilities.enabled === true && researchCapabilities.engineVersion === 'deep-research-v2'
          : import.meta.env.VITE_DEEP_RESEARCH_V2_ENABLED === 'true';
        const externalAvailable = v2 && researchCapabilities?.externalAcademic === true;
        if (researchSourcePolicy === 'academic_external' && !externalAvailable) {
          setComposerError('外部文献研究当前不可用，请改用任务材料或稍后重试。');
          return false;
        }
        const effectivePolicy = researchSourcePolicy;
        if (effectivePolicy === 'task_only' && !scope.allowedPaperIds.length) {
          if (externalAvailable) throw new Error('请先为任务加入研究材料，或在材料设置中开启补充外部文献。');
          throw new Error('请先为任务加入研究材料');
        }
        if (scope.allowedPaperIds.length && !materialReady(scope.allowedPaperIds)) return false;
        await research.start(task, sendText, {
          ...scope,
          engineVersion: v2 ? 'deep-research-v2' : 'legacy-v1',
          ...(v2 ? { engineVersion: 'deep-research-v2', sourcePolicy: { mode: effectivePolicy }, budgetProfile: researchBudgetProfile,
            contextRefs: researchContextRefs } : {}),
        });
      } catch (error) { inputError(error.message); return false; }
      return;
    }
    if (skill && !sendText && !['critique', 'compare', 'background'].includes(skill.skillId)) {
      await appendMessage(task.id, createMessage('ai', `请在 /${skill.command} 后写下你想解决的问题。`, { isSystem: true }));
      return;
    }
    const requestText = skill?.skillId === 'critique' ? sendText || '整体批判阅读这篇论文'
      : skill?.skillId === 'compare' ? `比较任务中相关论文的方法、实验、贡献与局限。${sendText}`
        : skill?.skillId === 'background' ? `解释理解论文所需的前置知识。${sendText}` : text;
    let context;
    let critiqueTargets;
    try {
      const explicitPaperIds = resolveNamedTaskPapers(text, papers, task.paperIds);
      const skillPaperIds = explicitPaperIds;
      context = resolveTaskContext(task, { text: requestText,
        ...((skill && startsNewCapability(skill.skillId)) || learning.inputMode === 'chat' ? { activity: null } : {}),
        ...(skillPaperIds !== undefined ? { paperIds: skillPaperIds } : {}) });
      if (followup) {
        const artifact = task.artifacts.find(item => (item.id || item.artifactId) === followup.artifactId);
        const ids = artifact?.critique?.scope?.allowedPaperIds || artifact?.paperIds || [];
        context = resolveTaskContext(task, { text: requestText, activity: null, paperIds: ids });
      }
      if (skill?.skillId === 'critique' || skill?.steps?.includes('critique')) {
        const all = /分别|逐篇|每篇|所有论文|全部论文|两篇|这些论文/u.test(text);
        critiqueTargets = followup?.regenerate ? task.artifacts.find(item => item.id === followup.artifactId)?.critique?.scope?.targetPaperIds : chosenTargets || explicitPaperIds || (all ? context.allowedPaperIds :
          context.primaryPaperId ? [context.primaryPaperId] : task.focusedPaperId ? [task.focusedPaperId] :
            context.allowedPaperIds.length === 1 ? context.allowedPaperIds : null);
        if (!critiqueTargets && !followup) {
          setCritiqueTargetChoice({ taskId: task.id, text, skill, paperIds: context.allowedPaperIds });
          return false;
        }
        if (critiqueTargets?.some(id => !context.allowedPaperIds.includes(id))) throw new Error('批判对象不属于当前材料。');
      }
      if ((skill?.skillId === 'compare' || skill?.steps?.includes('compare')) && context.allowedPaperIds.length < 2) throw new Error('比较至少需要两篇论文，请先在任务中加入论文。');
      if (skill?.skillId === 'critique' && context.allowedPaperIds.length === 0) throw new Error('请先加入并打开一篇论文。');
    }
    catch (error) { setComposerError(error.message); return false; }
    if (!materialReady(context.allowedPaperIds)) return false;
    await learning.operations.start(task, 'conversation.execute', {
      capability: skill?.skillId || 'chat', message: sendText || requestText,
      ...(skill?.steps ? { steps: skill.steps } : {}),
      displayText: materialDraft(text).text.trim(), allowedPaperIds: context.allowedPaperIds,
      primaryPaperId: context.primaryPaperId, strictScope: context.strictScope,
      ...(critiqueTargets ? { targetPaperIds: critiqueTargets } : {}),
      ...(followup ? { followup } : {}),
      expectedTaskRevision: task.revision,
    });
    setCritiqueSelection(null);
    setCritiqueTargetChoice(null);
  };
  const deleteMessage = async index => {
    const source = activeTask?.messages[index];
    if (activeTaskId && source) await updateTask(activeTaskId, task => ({ messages: task.messages.filter(message => source.id ? message.id !== source.id : message !== source) }));
  };
  const saveMessage = async (index, asArtifact = true) => {
    const taskId = activeTaskId;
    const source = activeTask?.messages[index];
    if (!taskId || !source) return false;
    const isUser = source.role === 'user';
    const sources = isUser ? documentSources(source.sourceAnchorId ? source : { sources: source.sources }) : documentSources(source);
    const matchesSource = message => source.id ? message.id === source.id : message === source
      || source.sourceRequestId && message.sourceRequestId === source.sourceRequestId && message.role === source.role;
    let saved;
    let collection = asArtifact && !isUser ? 'artifacts' : 'notes';
    await updateTask(taskId, task => {
      const currentIndex = task.messages.findIndex(matchesSource);
      if (currentIndex < 0) throw new Error('这条对话已移除，未保存其他消息。');
      const messageId = source.id || `legacy-message:${index}`;
      saved = null;
      for (const key of ['artifacts', 'notes']) {
        const existing = task[key].find(item => item.sourceMessageId === messageId
          || source.artifactId && (item.id || item.artifactId) === source.artifactId);
        if (existing) { saved = existing; collection = key; break; }
      }
      saved ||= { id: makeId(), title: (isUser ? String(source.content || '').trim().split(/\r?\n/u)[0].slice(0, 96) : questionTopic(task.messages.slice(0, currentIndex).findLast(message => message.role === 'user')?.content)) || '对话笔记', titleOrigin: 'generated',
        ...(!isUser && source.critique ? { critique: source.critique } : {}),
        capability: isUser ? undefined : source.capability,
        text: source.content, paperIds: isUser ? [...new Set(sources.map(item => item.pdfId || item.sourcePdfId).filter(Boolean))] : source.context?.allowedPaperIds || task.paperIds,
        sources, sentenceSourceMap: isUser ? [] : source.sentenceSourceMap || [], sourceMessageId: messageId,
        sourceRequestId: source.sourceRequestId, type: isUser ? 'note' : source.capability || 'note', createdAt: new Date().toISOString(), versions: [] };
      return {
        [collection]: task[collection].some(item => item.id === saved.id) ? task[collection] : [...task[collection], saved],
        messages: task.messages.map((message, position) => position === currentIndex ? { ...message, id: messageId, artifactId: saved.id } : message),
      };
    });
    return saved.id;
  };
  const createNote = async () => {
    if (!activeTaskId) return;
    const taskId = activeTaskId;
    const note = { id: makeId(), title: '未命名笔记', titleOrigin: 'user', type: 'note', text: '', paperIds: [], createdAt: new Date().toISOString(), versions: [] };
    await updateTask(taskId, task => ({ notes: [...task.notes, note] }));
    if (activeTaskIdRef.current === taskId) openDocument(note, 'notes', true);
  };
  const openDocument = (item, collection = null, startEditing = false) => {
    setRecoveryPreview(null);
    setSelectedLearning(null); setLocalError('');
    const source = collection || (activeTask?.artifacts.includes(item) ? 'artifacts' : 'notes');
    const index = activeTask?.[source]?.findIndex((candidate) => candidate === item || (item.id && candidate.id === item.id)) ?? -1;
    const selection = { taskId: activeTaskId, collection: source, index, id: item.id || item.artifactId, startEditing };
    let draft = null;
    selection.baseText = normalizeNoteContent(item);
    try {
      draft = localStorage.getItem(documentDraftKey(selection));
      if (draft !== null) {
        const base = localStorage.getItem(documentDraftKey(selection) + ':base');
        selection.baseText = base === null ? null : JSON.parse(base);
      }
    }
    catch { setLocalError('本地编辑草稿暂不可用'); }
    setSelectedDocument(selection);
    setDocumentDraft(draft ?? normalizeNoteContent(item));
    const view = { kind: 'document', collection: source, id: selection.id, index };
    storeView(activeTaskId, view, true); setReturnContent(view);
    patchLayout({ reader: true });
  };
  const openLearningRecord = activity => {
    const view = { kind: 'learning', id: activity.activityId || activity.id };
    setSelectedDocument(null); setRecoveryPreview(null); setLocalError('');
    setSelectedLearning({ taskId: activeTaskId, id: view.id });
    storeView(activeTaskId, view, true); setReturnContent(view); patchLayout({ reader: true });
  };
  const returnToPaper = () => {
    setReturnContent(null);
    setSelectedDocument(null); setSelectedLearning(null); setRecoveryPreview(null); setLocalError('');
    storeView(activeTaskId, { kind: 'paper' });
  };
  const openPreview = record => {
    setSelectedDocument(null); setSelectedLearning(null); setRecoveryPreview(record);
    const view = { kind: 'preview', record };
    storeView(activeTaskId, view, true); setReturnContent(view); patchLayout({ reader: true });
  };
  const reopenContent = view => {
    if (view?.kind === 'document') {
      const item = view.id ? activeTask?.[view.collection]?.find(entry => (entry.id || entry.artifactId) === view.id)
        : activeTask?.[view.collection]?.[view.index];
      if (item) { openDocument(item, view.collection); return true; }
    }
    if (view?.kind === 'learning') {
      const item = savedLearningActivities.find(entry => (entry.activityId || entry.id) === view.id)
        || ((activeTask?.activeActivity?.activityId || activeTask?.activeActivity?.id) === view.id ? activeTask.activeActivity : null);
      if (item) { openLearningRecord(item); return true; }
    }
    if (view?.kind === 'preview' && view.record?.taskId === activeTaskId) { openPreview(view.record); return true; }
    return false;
  };
  const restoreContent = useEffectEvent(reopenContent);
  useEffect(() => {
    if (!activeTask || restoredContentTask.current === activeTaskId) return;
    restoredContentTask.current = activeTaskId;
    try {
      setReturnContent(null);
      const view = JSON.parse(localStorage.getItem(contentViewKey(activeTaskId)) || 'null');
      if (view && view.kind !== 'paper' && !restoreContent(view)) setLocalError('上次打开的记录已移动或暂不可用，请从任务导航重新选择。');
    } catch { setLocalError('上次阅读位置暂不可用，任务记录仍保留。'); }
  }, [activeTaskId, activeTask]);
  const preview = recoveryPreview?.taskId === activeTaskId ? recoveryPreview : null;
  const recoverResult = async () => {
    if (!preview || savingRecovery) return;
    const selected = preview;
    setSavingRecovery(true);
    try {
      const receipt = await learning.operations.recoverResult(selected.taskId, selected.requestId);
      const artifact = receipt.task?.artifacts?.find(item => item.sourceRequestId === selected.requestId);
      if (!artifact) throw new Error('保存状态已确认，请在任务成果列表中查看');
      if (activeTaskIdRef.current === selected.taskId) {
        setRecoveryPreview(null);
        setSelectedDocument({ taskId: selected.taskId, collection: 'artifacts', id: artifact.id, baseText: artifact.text });
        setDocumentDraft(artifact.text);
      }
    } catch (error) { setLocalError(error.response?.data?.message || error.message || '成果保存未确认，请查询原请求'); }
    finally { setSavingRecovery(false); }
  };
  const activeDocument = selectedDocument?.taskId === activeTaskId ? (selectedDocument.id
    ? activeTask?.[selectedDocument.collection]?.find((item) => (item.id || item.artifactId) === selectedDocument.id)
    : activeTask?.[selectedDocument.collection]?.[selectedDocument.index]) : null;
  const selectedDocumentKey = selectedDocument ? documentDraftKey(selectedDocument) : null;
  const activeLearning = selectedLearning?.taskId === activeTaskId
    ? savedLearningActivities.find(item => (item.activityId || item.id) === selectedLearning.id)
      || ((activeTask?.activeActivity?.activityId || activeTask?.activeActivity?.id) === selectedLearning.id ? activeTask.activeActivity : null)
    : null;
  const contentPositionKey = activeDocument ? `pixiu-content-scroll:${selectedDocumentKey}`
    : activeLearning ? `pixiu-learning-scroll:${activeTaskId}:${selectedLearning.id}`
      : preview ? `pixiu-result-scroll:${activeTaskId}:${preview.requestId}` : null;
  useLayoutEffect(() => {
    const element = contentScrollRef.current;
    if (!element || !contentPositionKey) return;
    try { element.scrollTop = Number(localStorage.getItem(contentPositionKey)) || 0; } catch { /* Optional preference. */ }
    // Detached browser elements report scrollTop=0. Persist live scroll events
    // instead of overwriting the last position during unmount.
  }, [contentPositionKey]);
  const saveContentPosition = event => {
    if (contentPositionKey) { try { localStorage.setItem(contentPositionKey, String(event.currentTarget.scrollTop)); } catch { /* Optional preference. */ } }
  };
  const originalDocumentPage = documentOriginalPage(activeDocument);
  useEffect(() => { setDocumentEditing(Boolean(selectedDocument?.startEditing)); }, [selectedDocumentKey, selectedDocument?.startEditing]);
  const documentDirty = !!activeDocument && documentDraft !== normalizeNoteContent(activeDocument);
  const saveDocumentFromToolbar = async () => {
    if (savingDocument) return;
    setSavingDocument(true); setLocalError('');
    try { await saveDocument(); }
    catch (error) { setLocalError(error.response?.data?.message || error.message || '保存失败，草稿仍保留'); }
    finally { setSavingDocument(false); }
  };
  const saveDocument = async () => {
    if (!activeDocument || !selectedDocument) return;
    const { taskId, collection } = selectedDocument;
    try { await updateTask(taskId, (task) => {
      const entries = [...task[collection]];
      const index = selectedDocument.id ? entries.findIndex((item) => (item.id || item.artifactId) === selectedDocument.id) : selectedDocument.index;
      const previous = entries[index];
      if (!previous) throw new Error('文档已不存在，草稿仍保留');
      if (selectedDocument.baseText === null || normalizeNoteContent(previous) !== selectedDocument.baseText) {
        entries[index] = { ...previous, text: documentDraft };
        throw Object.assign(new Error('笔记已有新版本，草稿已保留。请核对最新正文后再保存。'),
          { code: 'DOCUMENT_CONFLICT', draftTask: { ...task, [collection]: entries } });
      }
      entries[index] = reviseDocument(previous, documentDraft);
      return { [collection]: entries };
    }); } catch (error) {
      if (error.code === 'DOCUMENT_CONFLICT') await taskWorkspaceRemoteStore.retainUnsyncedDraft(error.draftTask, 'document-conflict');
      throw error;
    }
    if (selectedDocumentRef.current && documentDraftKey(selectedDocumentRef.current) === documentDraftKey(selectedDocument)) {
      setSelectedDocument(previous => ({ ...previous, baseText: documentDraft }));
    }
    try {
      const key = documentDraftKey(selectedDocument);
      // Typing may have continued while the server save was pending.
      if (localStorage.getItem(key) === documentDraft) { localStorage.removeItem(key); localStorage.removeItem(key + ':base'); }
      else localStorage.setItem(key + ':base', JSON.stringify(documentDraft));
    } catch { setLocalError('正文已保存，本地草稿清理失败'); }
  };
  const exportDocument = () => {
    if (!activeDocument) return;
    const blob = new Blob([documentMarkdownExport(activeDocument, documentDraft, papers)], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = `${activeDocument.title || '笔记'}.md`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const renameDocument = async title => {
    const selection = selectedDocument;
    await updateTask(selection.taskId, task => {
      const entries = [...task[selection.collection]];
      const index = selection.id ? entries.findIndex(item => (item.id || item.artifactId) === selection.id) : selection.index;
      if (!entries[index]) throw new Error('文档已不存在，请刷新');
      entries[index] = { ...entries[index], title, titleOrigin: 'user' };
      return { [selection.collection]: entries };
    });
  };
  const runDocumentMove = async (targetTaskId, includeMaterials, queryOnly) => {
    const selection = selectedDocument;
    const key = documentDraftKey(selection) + ':move';
    let intent = JSON.parse(localStorage.getItem(key) || 'null');
    if (!intent && queryOnly) throw new Error('此文档没有待查询的移动请求');
    if (!intent) {
      if (documentDraft !== normalizeNoteContent(activeDocument)) throw new Error('请先保存正文再移动');
      const [source, target] = await Promise.all([taskWorkspaceApi.getTask(selection.taskId), taskWorkspaceApi.getTask(targetTaskId)]);
      const latest = source[selection.collection].find(item => (item.id || item.artifactId) === selection.id);
      if (!latest || normalizeNoteContent(latest) !== selection.baseText) throw new Error('文档已有新版本，请刷新核对后移动');
      intent = { requestId: makeId(), targetTaskId, documentId: selection.id, collection: selection.collection,
        sourceRevision: source.revision, targetRevision: target.revision, includeMaterials };
      localStorage.setItem(key, JSON.stringify(intent));
    } else if (!queryOnly && (intent.targetTaskId !== targetTaskId || intent.includeMaterials !== includeMaterials)) {
      throw new Error('先查询原移动请求，确认结果后再更改目标');
    }
    let result;
    try { result = queryOnly ? await taskWorkspaceApi.getDocumentMove(selection.taskId, intent.requestId)
      : await taskWorkspaceApi.moveDocument(selection.taskId, intent); }
    catch (error) {
      if ([400, 409].includes(error.response?.status)) localStorage.removeItem(key);
      throw error;
    }
    await workspace.adoptServerTask(result.sourceTask);
    await workspace.adoptServerTask(result.targetTask);
    localStorage.removeItem(key);
    if (selectedDocumentRef.current && documentDraftKey(selectedDocumentRef.current) === documentDraftKey(selection)) {
      setSelectedDocument(null); setDocumentDraft('');
    }
  };
  const moveDocument = async (...args) => {
    setMovingDocument(true);
    try { await runDocumentMove(...args); }
    finally { setMovingDocument(false); }
  };
  const restoreDocument = async (version) => {
    if (savingDocument) throw new Error('正在保存正文，请等待保存结果');
    if (movingDocument) throw new Error('正在移动文档，请等待结果确认');
    const selection = selectedDocument;
    const text = documentText(version);
    const draft = documentDraft;
    setRestoringDocument(true);
    try { await updateTask(selection.taskId, (task) => {
      const entries = [...task[selection.collection]];
      const index = selection.id ? entries.findIndex((item) => (item.id || item.artifactId) === selection.id) : selection.index;
      if (!entries[index]) throw new Error('文档已不存在，无法恢复');
      if (selection.baseText === null || normalizeNoteContent(entries[index]) !== selection.baseText) throw new Error('笔记已有新版本，请核对后再恢复。草稿仍保留。');
      entries[index] = reviseDocument(entries[index], text, { draft, restoredFrom: version.savedAt || 'legacy' });
      return { [selection.collection]: entries };
    });
    if (selectedDocumentRef.current && documentDraftKey(selectedDocumentRef.current) === documentDraftKey(selection)) {
      setDocumentDraft(text); setSelectedDocument(previous => ({ ...previous, baseText: text }));
    }
    try {
      const key = documentDraftKey(selection);
      if (localStorage.getItem(key) === draft) { localStorage.removeItem(key); localStorage.removeItem(key + ':base'); }
      else localStorage.setItem(key + ':base', JSON.stringify(text));
    }
    catch { setLocalError('版本已恢复，本地草稿清理失败'); }
    } finally { setRestoringDocument(false); }
  };
  const jumpToSource = async (source) => {
    const targetPaperId = source?.pdfId || source?.sourcePdfId || activeTask?.focusedPaperId;
    if (!targetPaperId || !activeTask?.paperIds.includes(targetPaperId)) return false;
    let index = Number(source.pageIndex ?? source.sourcePageIndex);
    if (source.literalQuote) {
      try {
        const db = await initDB();
        const { record } = await loadTaskMaterial(db, taskWorkspaceApi, activeTaskId, targetPaperId);
        index = await locatePdfQuote(record.blob, targetPaperId, source.literalQuote);
        if (index === null) {
          setLocalError('这处摘录暂不能唯一定位到PDF页面，原摘录仍可查看。');
          return false;
        }
      } catch {
        setLocalError('原文定位暂不可用，原摘录仍可查看。');
        return false;
      }
    }
    if (activeTaskIdRef.current !== activeTaskId) return false;
    const sourceReturn = selectedDocument ? { kind: 'document', collection: selectedDocument.collection, id: selectedDocument.id, index: selectedDocument.index }
      : selectedLearning ? { kind: 'learning', id: selectedLearning.id } : recoveryPreview ? { kind: 'preview', record: recoveryPreview } : null;
    setLocalError('');
    setSelectedDocument(null);
    setSelectedLearning(null);
    setRecoveryPreview(null);
    storeView(activeTaskId, { kind: 'paper' });
    if (targetPaperId !== activeTask.focusedPaperId) await openPaper(targetPaperId);
    if (activeTaskIdRef.current !== activeTaskId) return false;
    setReturnContent(sourceReturn);
    if (Number.isInteger(index) && index >= 0) setJump({ taskId: activeTaskId, pdfId: targetPaperId, pageIndex: index, token: Date.now(), anchorId: source.sourceAnchorId || source.sectionId || null });
    patchLayout({ reader: true });
    return true;
  };
  const syncPdfSelection = (content, role, _isSync, sourceMeta) => {
    const taskId = activeTaskId;
    const pdfId = paperView.id;
    if (!taskId || !pdfId || !content?.trim()) return;
    const context = { taskId, allowedPaperIds: [pdfId], primaryPaperId: pdfId, strictScope: true };
    void appendMessage(taskId, createMessage(role === 'user' ? 'user' : 'ai', content, {
      context,
      sourceAnchorId: sourceMeta?.sourceAnchorId,
      sourcePageIndex: sourceMeta?.sourcePageIndex,
      sourceText: sourceMeta?.sourceText,
      sourcePdfId: pdfId,
    }));
  };
  const captureTranslation = async (artifact) => {
    if (!activeTaskId || !paperView.id || !artifact) return false;
    const content = `${artifact.text || artifact.content || translationState.pages?.[page.pageIndex]?.translatedText || ''}`;
    if (!content.trim()) return false;
    const taskId = activeTaskId, pdfId = paperView.id, pageIndex = page.pageIndex;
    let saved;
    await updateTask(taskId, task => {
      const index = task.artifacts.findIndex(item => item.pageIndex === pageIndex && item.paperIds?.length === 1 && item.paperIds[0] === pdfId
        && (item.type === 'translation' || /译文/u.test(item.title || '')));
      const artifacts = [...task.artifacts];
      if (index >= 0) {
        const previous = artifacts[index];
        saved = normalizeNoteContent(previous) === content ? previous : { ...reviseDocument(previous, content), type: 'translation' };
        artifacts[index] = saved;
      } else {
        saved = { ...artifact, id: makeId(), type: 'translation', title: artifact.title || `${getPaperTitle(papers, pdfId)} · 第 ${pageIndex + 1} 页译文`,
          text: content, paperIds: [pdfId], pageIndex, createdAt: new Date().toISOString(), versions: [] };
        artifacts.push(saved);
      }
      return { artifacts };
    });
    return saved.id;
  };
  const currentTranslationPage = translationState.pages?.[page.pageIndex] || null;
  const goToPage = index => setJump({ taskId: activeTaskId, pdfId: focusedPaperId,
    pageIndex: index, token: Date.now(), anchorId: null });
  const outline = useMemo(() => buildPaperOutlineModel(paperView.deconstruct)?.items || [], [paperView.deconstruct]);
  const startResize = (event) => {
    event.preventDefault();
    const startX = event.clientX;
    const start = viewLayout.readerPercent;
    const move = (moveEvent) => setLayout((current) => ({ ...current, readerPercent: clamp(start + (moveEvent.clientX - startX) / viewLayout.available * 100, viewLayout.minPercent, viewLayout.maxPercent) }));
    const stop = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop); window.removeEventListener('pointercancel', stop); resizeCleanup.current = null; };
    resizeCleanup.current?.(); resizeCleanup.current = stop;
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', stop); window.addEventListener('pointercancel', stop);
  };
  const startNavigationResize = event => {
    event.preventDefault();
    const startX = event.clientX, start = viewLayout.navWidth;
    const move = moveEvent => patchLayout({ navWidth: clamp(start + moveEvent.clientX - startX, 200, Math.min(320, width - 832)) });
    const stop = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop); window.removeEventListener('pointercancel', stop); resizeCleanup.current = null; };
    resizeCleanup.current?.(); resizeCleanup.current = stop;
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', stop); window.addEventListener('pointercancel', stop);
  };
  const closeNavigation = (restoreFocus = true) => {
    setCompactNavigation(false);
    if (restoreFocus) {
      if (compact) compactNavigationButton.current?.focus();
      else navigationRef.current?.querySelector('button')?.focus();
    }
  };

  const timeline = useMemo(() => conversationTimeline(activeTask, learning.operations.records).map(message => {
    const sourceId = activeTask?.messages[message.originalIndex]?.id || message.id || `legacy-message:${message.originalIndex}`;
    const saved = [...(activeTask?.artifacts || []), ...(activeTask?.notes || [])].find(item => item.sourceMessageId === sourceId);
    const linked = saved || activeTask?.artifacts?.find(item => (item.id || item.artifactId) === message.artifactId);
    return { ...message, id: message.id ?? `legacy-message:${message.originalIndex}`, ...(saved ? { artifactId: saved.id || saved.artifactId } : {}),
      ...(linked?.critique?.schemaVersion === 2 && message.critique ? { artifactIsCurrent: critiqueMessageIsCurrent(linked, message) } : {}) };
  }), [activeTask, learning.operations.records]);
  const locateMessage = message => {
    if (!message) { setComposerError('未找到原对话，请尝试搜索相关问题。'); return; }
    setShowProcessingHistory(false); setCompactNavigation(false); setCompactPane('chat');
    patchLayout({ chat: true }); setFocusMessage({ id: message.id, token: Date.now() });
  };
  const locateOperation = record => locateMessage(timeline.find(message => message.role === 'user'
    && (message.sourceRequestId === record.requestId || message.timelineRequestIds?.includes(record.requestId))));
  const locateResearch = run => locateMessage(timeline.find(message => message.timelineResearchId === run.researchId));
  const locateLearning = activity => locateMessage(timeline.findLast(message => message.context?.activityId === (activity.activityId || activity.id)));
  const locateDocument = document => {
    if (document.sourceResearchId) { locateResearch({ researchId: document.sourceResearchId }); return; }
    const originalIndex = documentMessageIndex(activeTask, document);
    locateMessage(timeline.find(message => message.originalIndex === originalIndex));
  };
  const openArtifact = id => {
    const artifact = activeTask?.artifacts?.find(item => (item.id || item.artifactId) === id);
    const note = activeTask?.notes?.find(item => (item.id || item.artifactId) === id);
    if (artifact || note) { openDocument(artifact || note, artifact ? 'artifacts' : 'notes'); return; }
    const owner = tasks.find(task => task.artifacts?.some(item => (item.id || item.artifactId) === id));
    if (owner) { setRequestedDocument({ taskId: owner.id, id }); selectTask(owner.id); }
    else setComposerError('成果已移出或任务列表有更新，请刷新后查看。');
  };
  const openReport = (run, result) => {
    setShowProcessingHistory(false);
    const candidates = activeTask.artifacts.filter(item => item.sourceResearchId === run.researchId || item.sourceRunId === run.researchId || (item.id || item.artifactId) === `research:${run.researchId}:artifact`);
    const saved = candidates.find(item => item.origin === 'latest') || candidates.find(item => item.origin !== 'machine') || candidates.at(-1);
    if (saved) { openDocument(saved, 'artifacts'); return; }
    openPreview({ taskId: activeTaskId, requestId: run.researchId, kind: 'research.report', paperIds: run.paperIds,
      result: { artifact: { text: sanitizeResearchReport(typeof result.report === 'string' ? result.report : result.report?.body || '') }, sources: result.sources || (result.findings || []).flatMap(finding => finding.sources || []) } });
  };
  const handleAddSource = async (taskId, runId, sourceId) => {
    const task = taskRef.current.get(taskId);
    if (!task) throw new Error('任务不存在');
    const key = JSON.stringify(['source-add', taskId, runId, sourceId]);
    const intent = sourceAddIntents.current.get(key) || getResearchIntent(key, { expectedTaskRevision: task.revision });
    sourceAddIntents.current.set(key, intent);
    const response = await taskResearchApi.addSource(taskId, runId, sourceId, { ...intent.input, requestId: intent.requestId });
    if (response?.workspace) await workspace.adoptServerTask(response.workspace);
    if (response?.paperId) {
      sourceAddIntents.current.delete(key);
      clearResearchIntent(key);
    }
    return response;
  };
  const openOperationResult = record => { setShowProcessingHistory(false); openPreview(record); };
  const openPaperOverview = () => {
    const labels = { abstract: '摘要', introduction: '研究问题', methods: '方法', results: '结果', discussion: '讨论', conclusion: '结论' };
    const sections = Object.entries(paperView.deconstruct?.paper_skeleton || {}).filter(([, value]) => value && typeof value === 'string');
    openPreview({ taskId: activeTaskId, requestId: `overview:${paperView.id}`, kind: 'paper.overview', paperIds: [paperView.id],
      result: { artifact: { text: sections.map(([key, value]) => `## ${labels[key] || key}\n${value}`).join('\n\n') || '尚无可显示的概览。' } } });
  };
  const researchResult = run => research.runs[`${activeTaskId}/${run.researchId}`]
    || (activeTask?.artifacts.some(item => item.sourceResearchId === run.researchId || (item.id || item.artifactId) === `research:${run.researchId}:artifact`) ? { status: 'succeeded' } : null);
  const operationControls = {
    busy: Boolean(learning.busyTasks[activeTaskId]), onRetry: requestId => learning.operations.retry(activeTask, requestId),
    onSubmitSaved: requestId => learning.operations.submitSaved(activeTaskId, requestId),
    onRefresh: () => learning.operations.refresh(), onCancel: requestId => learning.operations.cancel(activeTaskId, requestId), onOpenResult: openOperationResult,
  };
  const pendingOperations = Object.values(learning.operations.records).filter(record => record.taskId === activeTaskId && !record.retriedBy
    && ['queued', 'running', 'unknown', 'awaiting_submission', 'cancelling'].includes(record.status));
  const currentLearning = activeTask?.activeActivity;
  const learningPaperIds = currentLearning?.snapshot?.paperIds || currentLearning?.paperIds || (currentLearning?.pdfId ? [currentLearning.pdfId] : []);
  let submittingLearningAnswer = currentLearning?.status === 'active' && learning.inputMode === 'answer'
    && !resolveConversationIntent(composerDraft).skill && critiqueSelection?.taskId !== activeTaskId;
  if (submittingLearningAnswer) {
    try {
      const named = resolveNamedTaskPapers(composerDraft, papers, activeTask.paperIds);
      const context = resolveTaskContext(activeTask, { text: composerDraft, ...(named !== undefined ? { paperIds: named } : {}) });
      submittingLearningAnswer = context.allowedPaperIds.length > 0 && context.allowedPaperIds.length === learningPaperIds.length
        && context.allowedPaperIds.every(id => learningPaperIds.includes(id));
    } catch { submittingLearningAnswer = false; }
  }
  const learningQuestionMessage = currentLearning?.status === 'active' && timeline.findLast(message => message.role !== 'user' && message.context?.activityId === currentLearning.activityId);
  const learningActions = currentLearning?.status === 'active' && <div className="unified-learning-question-actions" role="group" aria-label="学习问题操作">
    {!learning.completionSuggested && <button type="button" disabled={learning.busyTasks[activeTaskId]} onClick={() => { learning.setInputMode('answer'); locateLearning(currentLearning); }}>回答这道题</button>}
    <WorkbenchPopover label="学习帮助">{close => <>{[['hint', '给我提示'], ['remediate', '补充基础'], ['retry', '重新回答'], ['skip', '跳过本题'], ['pause', '暂停学习'], ['finish', '结束学习']].map(([action, label]) => <button type="button" key={action} disabled={learning.busyTasks[activeTaskId]} onClick={() => { learning.act(activeTask, action); close(); }}>{label}</button>)}</>}</WorkbenchPopover>
    {learning.completionSuggested && <button type="button" disabled={learning.busyTasks[activeTaskId]} onClick={() => learning.act(activeTask, 'finish')}>完成本轮学习</button>}
  </div>;
  const pendingResearch = (activeTask?.researchRuns || []).filter(run => {
    const result = researchResult(run);
    return !result || !['succeeded', 'completed', 'failed', 'cancelled'].includes(result.status);
  });
  const activityEntries = [
    ...pendingOperations.map(record => ({ id: record.requestId, status: record.status, label: operationStatusText(record), isRequest: true, locate: () => locateOperation(record),
      ...(record.status !== 'cancelling' ? { stop: () => learning.operations.cancel(activeTaskId, record.requestId), stopLabel: '停止' } : {}) })),
    ...pendingResearch.map(run => ({ id: run.researchId, status: researchResult(run)?.status, label: `研究 · ${researchResult(run) ? getResearchStatusMeta(researchResult(run).status).label : '正在读取'}`, locate: () => locateResearch(run),
      stop: () => research.action(activeTaskId, run.researchId, 'cancel') })),
    ...(currentLearning?.status === 'active' && learning.inputMode !== 'chat' && !pendingOperations.length ? [{ id: currentLearning.activityId, status: currentLearning.status,
      label: `${currentLearning.mode === 'quiz' ? '自测' : '精读'} · ${learning.completionSuggested ? '可结束本轮' : '待回答'}`, locate: () => locateLearning(currentLearning) }] : []),
  ].sort((left, right) => activityPriority(left.status) - activityPriority(right.status));
  const renderAfterMessage = message => {
    const run = message.timelineResearchId && activeTask.researchRuns?.find(item => item.researchId === message.timelineResearchId);
    const record = message.timelineOperationId && learning.operations.records[message.timelineOperationId];
    const history = message.role !== 'user' && savedLearningActivities.find(activity => message.context?.activityId === (activity.activityId || activity.id)
      && !timeline.some(other => other.role !== 'user' && other.context?.activityId === message.context.activityId && other.orderIndex > message.orderIndex));
    return <>
      {run && <ResearchCard taskId={activeTaskId} run={run} result={researchResult(run)} error={research.errors?.[JSON.stringify([activeTaskId, run.researchId])]}
        compactTitle={activeTask.artifacts.find(item => item.sourceResearchId === run.researchId || (item.id || item.artifactId) === `research:${run.researchId}:artifact`)?.title}
        onRefresh={research.refresh}
        onAction={research.action} onJumpToSource={jumpToSource} onOpenReport={openReport} onAddSource={handleAddSource} />}
      {record && record.status !== 'succeeded' && !record.retriedBy && !run && <OperationRecord record={record} showQuestion={false} {...operationControls} />}
      {learningQuestionMessage && message.orderIndex === learningQuestionMessage.orderIndex && learningActions}
      {history && <button type="button" className="unified-record-entry" onClick={() => openLearningRecord(history)}>{history.mode === 'quiz' ? '自测' : '精读'}{history.status === 'paused' ? '已暂停' : '已结束'} · 查看记录</button>}
    </>;
  };
  const currentActivityBar = activityEntries.length > 0 ? <div className="unified-current-activity" aria-label="当前活动">
    <button type="button" onClick={activityEntries[0].locate}>{activityEntries[0].label}{!activityEntries[0].isRequest && ' · 查看'}</button>
    {activityEntries[0].stop && <button type="button" onClick={() => activityEntries[0].stop()}>{activityEntries[0].stopLabel || '停止研究'}</button>}
    {activityEntries.length > 1 && <details><summary>另有 {activityEntries.length - 1} 项</summary>{activityEntries.slice(1).map(entry => <button type="button" key={entry.id} onClick={entry.locate}>{entry.label}{!entry.isRequest && ' · 查看'}</button>)}</details>}
  </div> : null;
  let draftPrimaryPaperId = null;
  if (activeTask && composerDraft.trim() && !/@\{/u.test(composerDraft)) {
    try {
      const skill = resolveConversationIntent(composerDraft).skill;
      draftPrimaryPaperId = resolveTaskContext(activeTask, { text: composerDraft,
        ...((skill && startsNewCapability(skill.skillId)) || learning.inputMode === 'chat' ? { activity: null } : {}),
        paperIds: resolveNamedTaskPapers(composerDraft, papers, activeTask.paperIds) }).primaryPaperId;
    } catch { /* Submission explains an ambiguous scope without guessing its primary paper. */ }
  }
  const composerContext = <>
    {(draftPrimaryPaperId || critiqueSelection?.taskId === activeTaskId || currentLearning?.status === 'active') && <div className="unified-composer-context">
      {draftPrimaryPaperId && <span>主要参考 {shortPaperTitle(papers, draftPrimaryPaperId)}</span>}
      {critiqueSelection?.taskId === activeTaskId && <span>{critiqueSelection.followup.regenerate ? '重新核查' : '正在追问：'} {critiqueSelection.title || '批判成果'}
        <button type="button" onClick={() => setCritiqueSelection(null)}>取消追问关联</button></span>}
      {currentLearning?.status === 'active' && <>
        {learning.inputMode === 'answer' ? <><span>正在回答学习问题</span><button type="button" onClick={() => learning.setInputMode('chat')}>改为普通提问</button></> : learningQuestionMessage && <button type="button" onClick={() => locateLearning(currentLearning)}>回到学习问题</button>}
        {!learningQuestionMessage && learningActions}
      </>}
    </div>}
    {intentChoice?.taskId === activeTaskId && <div className="unified-intent-choice" role="group" aria-label="选择分析重点">
      <span>{intentChoice.prompt}</span>{intentChoice.choices.map(choice => <button type="button" key={choice.skill.skillId} disabled={learning.busyTasks[activeTaskId]} onClick={() => sendMessage(intentChoice.text, choice.skill)}>{choice.label}</button>)}
      <button type="button" onClick={() => setIntentChoice(null)}>取消</button>
    </div>}
    {critiqueTargetChoice?.taskId === activeTaskId && <div className="unified-intent-choice" role="group" aria-label="选择批判对象">
      <span>要批判哪篇论文？</span>
      {critiqueTargetChoice.paperIds.map(id => <button type="button" key={id}
        onClick={() => sendMessage(critiqueTargetChoice.text, critiqueTargetChoice.skill, [id])}>{shortPaperTitle(papers, id)}</button>)}
      <button type="button" onClick={() => sendMessage(critiqueTargetChoice.text, critiqueTargetChoice.skill, critiqueTargetChoice.paperIds)}>分别分析全部</button>
      <button type="button" onClick={() => setCritiqueTargetChoice(null)}>取消</button>
    </div>}
    {composerError && <p className="unified-inline-error" role="alert">{composerError}<button type="button" onClick={() => setComposerError('')}>收起</button></p>}
    {learning.error && !Object.values(learning.operations.records).some(record => record.taskId === activeTaskId && record.error === learning.error) && <details className="unified-inline-error"><summary>暂时无法确认结果</summary>
      <p>{learning.error}</p><button type="button" onClick={() => setShowProcessingHistory(true)}>查看处理记录</button><button type="button" onClick={() => learning.operations.refresh()}>查询状态</button></details>}
  </>;

  const documentActions = activeDocument && <DocumentActions key={selectedDocumentKey} document={activeDocument} editing={documentEditing} dirty={documentDirty}
    researchVersions={activeDocument.sourceRunId ? activeTask.artifacts.filter(item => item.sourceRunId === activeDocument.sourceRunId) : []}
    onOpenVersion={version => openDocument(version, 'artifacts')}
    kind={selectedDocument.collection === 'notes' ? '笔记' : '成果'}
    displayTitle={documentDisplayTitle(activeDocument, activeTask, papers)}
    getPendingMove={() => { try { return JSON.parse(localStorage.getItem(selectedDocumentKey + ':move') || 'null'); } catch { return null; } }}
    saving={savingDocument} disabled={restoringDocument || movingDocument} onEdit={() => setDocumentEditing(value => !value)} onSave={saveDocumentFromToolbar}
    onLocate={(activeDocument.sourceMessageId || activeDocument.sourceRequestId || activeDocument.sourceResearchId || activeTask.messages.some(message => message.artifactId === (activeDocument.id || activeDocument.artifactId))) ? () => locateDocument(activeDocument) : undefined}
    onRecheck={activeDocument.critique?.schemaVersion === 2 ? () => prepareCritiqueRegeneration(activeDocument) : undefined}
    recheckDisabled={documentDirty || savingDocument || learning.busyTasks[activeTaskId]}
    onRestore={restoreDocument} taskId={activeTaskId} tasks={tasks} onRename={renameDocument} onMove={moveDocument} onExport={exportDocument} />;

  return <div className="unified-app theme-app-shell">
    <header className="unified-header theme-panel theme-border">
      <div className="unified-brand"><img src="/貔貅紫白.png" alt="" /> <strong>貔貅</strong></div>
      <TaskSwitcher tasks={tasks} activeTask={activeTask} onSelect={selectTask}
        onCreate={async () => { await createTask({ title: '新任务' }); setCompactPane('chat'); }}
        onRename={title => updateTask(activeTaskId, { title })} onArchive={async archived => {
          const saved = await updateTask(activeTaskId, { archived });
          if (saved?.archived !== archived) throw new Error('服务端尚未保存归档状态，请稍后重试。');
        }}>
        <button type="button" disabled={!activeTask} onClick={() => setShowProcessingHistory(true)}>处理记录</button>
        <TaskDraftRecovery taskId={activeTaskId} refreshKey={workspace.error || localError} onCreateTask={createTask} />
      </TaskSwitcher>
      <div className="unified-header-spacer" />
      <WorkbenchPopover label="布局" className="unified-layout-picker" trigger={<span className={`unified-layout-glyph layout-${compact ? compactPane : layout.reader && layout.chat ? 'split' : layout.reader ? 'reader' : 'chat'}`} aria-hidden="true"><i /><i /></span>}>
        {close => <><div className="workbench-menu-caption">切换布局</div>{[['split', '阅读与对话'], ['reader', '仅阅读'], ['chat', '仅对话']].filter(([mode]) => !compact || mode !== 'split').map(([mode, label]) => <button type="button" key={mode} aria-pressed={(compact ? compactPane : layout.reader && layout.chat ? 'split' : layout.reader ? 'reader' : 'chat') === mode} onClick={() => { setMode(mode); close(); }}><span className={`unified-layout-glyph layout-${mode}`} aria-hidden="true"><i /><i /></span><span>{label}</span></button>)}
          {!compact && width < 1360 && <button type="button" disabled={!viewLayout.canPinNavigation} aria-pressed={layout.navPinnedMedium}
            onClick={() => { patchLayout({ navPinnedMedium: !layout.navPinnedMedium, navigation: true }); close(); }}>{layout.navPinnedMedium ? '导航按需展开' : '固定导航'}</button>}
          </>}
      </WorkbenchPopover>
      <button type="button" className="workbench-popover-trigger" onClick={toggleTheme} title={theme === 'dark' ? '切换为浅色外观' : '切换为深色外观'} aria-label={theme === 'dark' ? '切换为浅色外观' : '切换为深色外观'}>
        {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
      </button>
    </header>
    {compact && <div className="unified-compact-switch" role="group" aria-label="内容视图">
      <button type="button" ref={compactNavigationButton} aria-expanded={compactNavigation} aria-controls="unified-navigation" onClick={() => setCompactNavigation(value => !value)}>任务与材料</button>
      <button type="button" ref={compactReaderButton} aria-pressed={compactPane === 'reader'} onClick={() => { setCompactPane('reader'); setCompactNavigation(false); }}>阅读</button>
      <button type="button" aria-pressed={compactPane === 'chat'} onClick={() => { setCompactPane('chat'); setCompactNavigation(false); }}>对话</button>
    </div>}
    <main className="unified-main" data-compact-pane={compactPane} data-navigation-drawer={viewLayout.drawer ? 'true' : undefined} data-drawer-open={drawerOpen ? 'true' : undefined} onKeyDown={event => {
      if (event.key === 'Escape' && drawerOpen) { event.preventDefault(); closeNavigation(); }
      if (event.key === 'Tab' && drawerOpen) {
        const items = [...(navigationRef.current?.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), summary, [tabindex="0"]') || [])].filter(node => node.getClientRects().length);
        if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1)?.focus(); }
        if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0]?.focus(); }
      }
    }}>
      {drawerOpen && <button type="button" tabIndex={-1} className="unified-navigation-backdrop" aria-label="关闭任务导航" onClick={() => closeNavigation()} />}
      <div id="unified-navigation" ref={navigationRef} role={drawerOpen ? 'dialog' : undefined} aria-modal={drawerOpen ? true : undefined} aria-label={drawerOpen ? '任务与材料' : undefined}
        className={`unified-task-nav ${compact && !drawerOpen ? 'unified-compact-hidden' : ''}`} style={{ width: viewLayout.navigation ? viewLayout.navWidth : 48 }}>
        <TaskNavigation tasks={tasks} activeTask={activeTask} papers={papers} collapsed={!viewLayout.navigation && !drawerOpen} onToggle={() => {
          if (viewLayout.drawer) { if (drawerOpen) closeNavigation(); else setCompactNavigation(true); }
          else patchLayout({ navigation: !layout.navigation });
        }}
          onSelectTask={id => { selectTask(id); setCompactNavigation(false); compactNavigationButton.current?.focus(); }} onCreateTask={async () => { await createTask({ title: '新任务' }); setCompactNavigation(false); setCompactPane('chat'); }} onOpenPaper={openPaper} onAddPaper={addPaper} onRemovePaper={removePaper} onOpenArtifact={openDocument}
          onOpenTaskDocument={(taskId, item) => { setRequestedDocument({ taskId, id: item.id || item.artifactId }); selectTask(taskId); setCompactNavigation(false); }}
          taskControlsInHeader onCreateNote={createNote} onUpload={() => fileInputRef.current?.click()} uploading={uploading} onCancelUpload={cancelUpload}
          learningRecords={savedLearningActivities} onOpenLearning={openLearningRecord} selectedDocumentId={selectedDocument?.id} selectedLearningId={selectedLearning?.id}>
          {(libraryError || materialError) && <p className="unified-inline-error" role="alert">{materialError || libraryError}</p>}
          {focusedPaperId && <div className="unified-outline">
            <button type="button" aria-expanded={showOutline} onClick={toggleOutline}>{showOutline ? <ChevronLeft size={13} /> : <ChevronRight size={13} />} 当前论文目录</button>
            {showOutline && <div>{outline.map((item) => <button type="button" key={item.id} style={{ paddingLeft: `${Math.max(0, item.level - 1) * 12 + 8}px` }} onClick={() => item.pageIndex != null && jumpToSource({ pdfId: focusedPaperId, pageIndex: item.pageIndex })}>{item.label}</button>)}{outline.length === 0 && <span>暂无目录</span>}</div>}
          </div>}
        </TaskNavigation>
      </div>
      {viewLayout.navigation && <div className="unified-resizer unified-nav-resizer" role="separator" tabIndex={0} aria-orientation="vertical" aria-label="调整导航宽度" aria-valuemin={200} aria-valuemax={Math.min(320, width - 832)} aria-valuenow={viewLayout.navWidth} onPointerDown={startNavigationResize} onKeyDown={event => {
        const steps = { ArrowLeft: -8, ArrowRight: 8 };
        if (!(event.key in steps) && !['Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        patchLayout({ navWidth: event.key === 'Home' ? 200 : event.key === 'End' ? Math.min(320, width - 832) : clamp(viewLayout.navWidth + steps[event.key], 200, Math.min(320, width - 832)) });
      }} />}
      <section ref={readerRef} className={`unified-reader ${!layout.reader ? 'unified-desktop-hidden' : ''}`} inert={drawerOpen ? true : undefined} style={{ flexBasis: layout.chat ? `${viewLayout.readerPercent}%` : '100%' }} aria-label="论文与成果">
        <div className="unified-pane-head">
          <BookOpen size={17} />
          {activeDocument ? <strong>{selectedDocument.collection === 'notes' ? '笔记' : '成果'}</strong> : <strong title={focusedPaperId ? getPaperTitle(papers, focusedPaperId) : ''}>{preview ? preview.kind === 'research.report' ? '研究报告' : '已生成结果' : activeLearning ? '学习记录' : focusedPaperId ? shortPaperTitle(papers, focusedPaperId) : '阅读区'}</strong>}
          {(activeDocument || activeLearning || preview) && focusedPaperId && <button type="button" onClick={returnToPaper}>查看原文</button>}
          {documentActions}
          {!activeDocument && !activeLearning && !preview && returnContent && <button type="button" onClick={() => { if (!reopenContent(returnContent)) setLocalError('这份记录已移动或暂不可用。'); }}>{returnContent.kind === 'learning' ? '返回学习记录' : returnContent.collection === 'notes' ? '返回笔记' : '返回成果'}</button>}
          {!activeDocument && !activeLearning && !preview && paperView.url && <div className="unified-translation-modes" role="group" aria-label="翻译视图">
            <button type="button" className={translationMode === 'original' ? 'active' : ''} onClick={() => setTranslationMode('original')}>原文</button>
            <button type="button" title={['success','partial'].includes(currentTranslationPage?.status) ? '查看已保存译文' : currentTranslationPage?.status === 'error' ? '查看翻译状态，重试需手动操作' : '打开后翻译当前页'} className={translationMode === 'translation' ? 'active' : ''} onClick={() => setTranslationMode('translation')}>译文</button>
            <button type="button" title={['success','partial'].includes(currentTranslationPage?.status) ? '对照原文与已保存译文' : '对照原文并翻译当前页'} className={translationMode === 'parallel' ? 'active' : ''} onClick={() => setTranslationMode('parallel')}>对照</button>
          </div>}
          <button type="button" className="unified-pane-hide" title="向左收起阅读区" onClick={() => patchLayout({ reader: false, chat: true, mode: 'chat' })} aria-label="收起阅读区"><PanelLeftClose size={16} /></button>
        </div>
        {localError && <div className="unified-inline-error workbench-reader-error" role="alert"><span>{localError}</span><button type="button" onClick={() => setLocalError('')}>收起</button></div>}
        {narrowParallel && !activeDocument && !activeLearning && !preview && paperView.url && <div className="unified-translation-narrow" role="group" aria-label="同页对照">
          <span>空间较窄，切换同页原文与译文</span>
          <button type="button" aria-pressed={narrowTranslationSide === 'original'} onClick={() => setNarrowTranslationSide('original')}>看原文</button>
          <button type="button" aria-pressed={narrowTranslationSide === 'translation'} onClick={() => setNarrowTranslationSide('translation')}>看译文</button>
          {!compact && layout.chat && <button type="button" onClick={() => setMode('reader')}>仅阅读</button>}
        </div>}
        <div className="unified-reader-body">
        {preview ? <div className="unified-document" ref={contentScrollRef} onScroll={saveContentPosition} aria-label="查看已生成结果">
          {!['research.report', 'paper.overview'].includes(preview.kind) && <div className="unified-document-toolbar"><button type="button" disabled={savingRecovery || (preview.paperIds || preview.result?.materialScope?.allowedPaperIds || []).some(id => !activeTask.paperIds.includes(id))} onClick={recoverResult}><Save size={15} /> {savingRecovery ? '正在保存…' : '保存为成果'}</button></div>}
          <p>{preview.kind === 'paper.overview' ? '论文概览' : preview.kind === 'research.report' ? '研究报告预览' : '保存完整结果，保留当前学习位置。'}</p>
          {(preview.paperIds || preview.result?.materialScope?.allowedPaperIds || []).some(id => !activeTask.paperIds.includes(id)) && <p role="status">请先恢复原请求材料，再保存成果。</p>}
          <div className="unified-document-preview"><CritiqueContent key={contentPositionKey} value={preview.result || {}} target="artifact" papers={papers} storageKey={contentPositionKey}
            text={preview.result?.artifact?.text || preview.result?.message || preview.result?.reply} onJumpToSource={jumpToSource} /></div>
          <CollapsedSources key={contentPositionKey} storageKey={`${contentPositionKey}:sources`} value={{ sources: preview.result?.sources || [] }} onJumpToSource={jumpToSource} />
        </div> : activeLearning ? <div className="unified-document" ref={contentScrollRef} onScroll={saveContentPosition}>
          <div className="unified-document-toolbar"><button type="button" onClick={() => locateLearning(activeLearning)}>定位原对话</button>
            {currentLearning?.activityId === activeLearning.activityId && currentLearning.status === 'paused' && <button type="button" disabled={learning.busyTasks[activeTaskId]} onClick={async () => { await learning.act(activeTask, 'resume'); setCompactPane('chat'); }}>继续学习</button>}
          </div>
          <LearningRecordContent activity={activeLearning} papers={papers} />
        </div> : activeDocument ? <div className="unified-document" ref={contentScrollRef} onScroll={saveContentPosition}>
          {(selectedDocument.baseText === null || normalizeNoteContent(activeDocument) !== selectedDocument.baseText) && <div role="alert">
            <p>笔记已有新版本，请核对后再保存。当前草稿已保留。</p>
            <details><summary>最新已保存正文</summary><MarkdownContent>{normalizeNoteContent(activeDocument)}</MarkdownContent></details>
            <button type="button" onClick={() => {
              const baseText = normalizeNoteContent(activeDocument);
              setSelectedDocument(previous => ({ ...previous, baseText }));
              try { localStorage.setItem(documentDraftKey(selectedDocument) + ':base', JSON.stringify(baseText)); }
              catch { setLocalError('草稿核对记录保存失败，请保留当前正文'); }
            }}>已核对，保留我的修改</button>
          </div>}
          <h1 className="workbench-document-heading" aria-label={documentDisplayTitle(activeDocument, activeTask, papers)}><DocumentTitle key={selectedDocumentKey} title={documentDisplayTitle(activeDocument, activeTask, papers)} onRename={activeDocument.origin === 'machine' ? undefined : renameDocument} /></h1>
          {documentEditing ? <>
          <textarea aria-label="编辑笔记与成果" disabled={restoringDocument || movingDocument} value={documentDraft} onChange={(event) => {
            const value = event.target.value;
            setDocumentDraft(value);
            try {
              const key = documentDraftKey(selectedDocument);
              localStorage.setItem(key, value);
              if (localStorage.getItem(key + ':base') === null) localStorage.setItem(key + ':base', JSON.stringify(selectedDocument.baseText));
            }
            catch { setLocalError('本地草稿保存失败，请先保存或下载当前正文'); }
          }} />
          <details className="unified-document-edit-preview"><summary>预览</summary><MarkdownContent>{documentDraft || '（空白正文）'}</MarkdownContent></details>
          </> : <article className="unified-document-body" aria-label="成果正文"><CritiqueContent key={contentPositionKey} papers={papers} storageKey={contentPositionKey}
            value={{ ...activeDocument, edited: activeDocument.edited || documentDirty }} target="artifact"
            text={documentDraft || '（空白正文）'} onJumpToSource={jumpToSource}
            onFollowup={issueId => selectCritiqueIssue(activeDocument.id || activeDocument.artifactId, issueId)} /></article>}
          {(activeDocument.critique?.schemaVersion !== 2 || activeDocument.edited) && <CollapsedSources key={contentPositionKey} storageKey={`${contentPositionKey}:sources`} value={activeDocument} onJumpToSource={jumpToSource} />}
          {activeDocument.critique?.schemaVersion !== 2 && originalDocumentPage && activeTask.paperIds.includes(originalDocumentPage.pdfId) &&
            <DocumentOriginalPage key={selectedDocumentKey} taskId={activeTaskId} source={originalDocumentPage}
              title={documentDisplayTitle(activeDocument, activeTask, papers)} text={documentDraft} paperTitle={getPaperTitle(papers, originalDocumentPage.pdfId)} />}
        </div> : null}
        <div className="unified-reader-paper" style={{ visibility: activeDocument || activeLearning || preview ? 'hidden' : 'visible', opacity: activeDocument || activeLearning || preview ? 0 : 1, pointerEvents: activeDocument || activeLearning || preview ? 'none' : undefined }}
          aria-hidden={Boolean(activeDocument || activeLearning || preview)} inert={activeDocument || activeLearning || preview ? true : undefined}>
        {paperView.metadata ? <div className="unified-empty">
          <h2>{paperView.metadata.title || getPaperTitle(papers, paperView.id)}</h2>
          <p>已加入论文信息，尚无可阅读的全文。</p>
          {paperView.metadata.abstract && <p>{paperView.metadata.abstract}</p>}
          {/^https:\/\/arxiv\.org\/abs\//u.test(paperView.metadata.url || '') && <a href={paperView.metadata.url} target="_blank" rel="noopener noreferrer">查看来源页面</a>}
        </div> : paperView.error ? <div className="unified-empty" role="alert">{paperView.error}</div>
          : paperView.url ? <div className={`unified-reader-content unified-reader-content-${displayedTranslationMode}`}>
            <div className="unified-pdf" aria-hidden={displayedTranslationMode === 'translation'} inert={displayedTranslationMode === 'translation' ? true : undefined}>
              {paperView.deconstruct?.processingStatus && <div className="unified-material-status" role="status">
                {['queued', 'parsing'].includes(paperView.deconstruct.processingStatus) ? '原文可阅读，正文正在解析…'
                  : paperView.deconstruct.questionReady ? '正文已就绪' : paperView.deconstruct.processingError || paperView.deconstruct.parseMessage || '原文可阅读，正文尚未就绪'}
                {['failed', 'interrupted', 'degraded'].includes(paperView.deconstruct.processingStatus) && !paperView.deconstruct.questionReady && <button type="button" disabled={processingRequest} onClick={() => requestMaterialProcessing(false)}>重试解析</button>}
                {paperView.deconstruct.aiAnalysisStatus === 'running' ? <span> · 正在生成概览…</span>
                  : paperView.deconstruct.questionReady && ['not_requested', 'failed', 'interrupted'].includes(paperView.deconstruct.aiAnalysisStatus) && <button type="button" disabled={processingRequest} onClick={() => requestMaterialProcessing(true)}>{paperView.deconstruct.aiAnalysisStatus === 'not_requested' ? '生成论文概览' : '重试论文概览'}</button>}
                {paperView.deconstruct.aiAnalysisStatus === 'completed' && <button type="button" onClick={openPaperOverview}>查看论文概览</button>}
              </div>}
              <PdfViewer key={`${activeTaskId}:${paperView.id}`} readingKey={`${activeTaskId}:${paperView.id}`} active={!activeDocument && !activeLearning && !preview && displayedTranslationMode !== 'translation' && (compact ? compactPane === 'reader' && !compactNavigation : layout.reader)} fileUrl={paperView.url} pdfId={paperView.id} paperSkeleton={paperView.deconstruct?.paper_skeleton || null} theme={theme} parseStatus={paperView.deconstruct?.parseStatus || papers.find((paper) => paper.id === paperView.id)?.parseStatus || null} initialHighlights={paperView.highlights}
              onPageChange={next => {
                if (!selectedDocumentRef.current && !selectedLearningRef.current && !recoveryPreviewRef.current) handlePdfPageChange(next);
                else if (next.totalPages > 0) setPage(current => ({ ...current, totalPages: next.totalPages }));
              }}
              onPageTextExtracted={next => { if (!selectedDocumentRef.current && !recoveryPreviewRef.current) handlePageTextExtracted(next); }} onSelection={syncPdfSelection}
              onHighlightsChange={async (highlights) => { const db = await initDB(); await db.put('highlightStore', highlights, paperView.id); }}
              onSaveNote={async payload => {
                if (!activeTaskId || !paperView.id) throw new Error('请先打开任务论文');
                const note = selectionNote(payload, paperView.id, makeId());
                await updateTask(activeTaskId, task => ({ notes: [...task.notes, note] }));
              }}
              targetPageIndex={jump.pdfId === paperView.id && jump.taskId === activeTaskId ? jump.pageIndex : initialPaperPage} targetPageJumpToken={jump.pdfId === paperView.id && jump.taskId === activeTaskId ? jump.token : 0} focusedSourceAnchorId={jump.pdfId === paperView.id && jump.taskId === activeTaskId ? jump.anchorId : null} focusedSourceAnchorToken={jump.pdfId === paperView.id && jump.taskId === activeTaskId ? jump.token : 0} /></div>
            {displayedTranslationMode !== 'original' && <div className="unified-translation"><TranslationPanel pdfId={paperView.id} fileUrl={paperView.url} pdfFileName={getPaperTitle(papers, paperView.id)} currentPage={page.pageIndex}
              pageData={currentTranslationPage?.status === 'translating' ? { ...currentTranslationPage, status: 'loading' } : currentTranslationPage}
              savedArtifactId={activeTask?.artifacts.find(item => item.pageIndex === page.pageIndex && item.paperIds?.length === 1 && item.paperIds[0] === focusedPaperId && (item.type === 'translation' || /译文/u.test(item.title || '')) && normalizeNoteContent(item) === currentTranslationPage?.translatedText)?.id}
              onOpenArtifact={openArtifact} onRetry={() => handleRetryTranslation(translationState)} onCancel={() => handleCancelTranslation(page.pageIndex)} onCaptureArtifact={captureTranslation} /></div>}
          </div>
            : focusedPaperId ? <div className="workbench-reader-loading" role="status" aria-label="正在打开论文"><span className="workbench-loading-title" /><span /><span /><span /><p>正在打开论文…</p></div>
            : workspace.ready === false ? <div className="workbench-reader-loading" role="status" aria-label="正在读取任务"><span className="workbench-loading-title" /><span /><span /><span /><p>正在读取任务…</p></div>
            : <div className="unified-empty"><FilePlus2 size={32} />
              <strong>{activeTask?.paperIds.length ? '选择一篇论文开始阅读' : '从一篇论文开始'}</strong>
              <p>{activeTask?.paperIds.length ? '在左侧选择论文；对话可以使用当前任务的全部材料。' : '上传 PDF 后即可阅读，再从对话中精读、补课或自测。'}</p>
              {uploading ? <p role="status">正在上传论文，请稍候…</p> : <button type="button" disabled={workspace.ready === false} onClick={() => activeTask?.paperIds.length ? openPaper(activeTask.paperIds[0]) : fileInputRef.current?.click()}>{activeTask?.paperIds.length ? '打开任务论文' : '上传论文'}</button>}
            </div>}
        {paperView.url && <PaperPageNavigation pageIndex={page.pageIndex} totalPages={page.totalPages} onJump={goToPage} />}
        </div>
        </div>
      </section>
      {layout.reader && layout.chat && !compact && <div className="unified-resizer" role="separator" tabIndex={drawerOpen ? -1 : 0} inert={drawerOpen ? true : undefined} aria-orientation="vertical" aria-label="调整阅读与对话宽度" aria-valuemin={Number(viewLayout.minPercent.toFixed(2))} aria-valuemax={Number(viewLayout.maxPercent.toFixed(2))} aria-valuenow={Number(viewLayout.readerPercent.toFixed(2))} onPointerDown={startResize} onKeyDown={event => {
        const steps = { ArrowLeft: -2, ArrowRight: 2 };
        if (!(event.key in steps) && !['Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const readerPercent = event.key === 'Home' ? viewLayout.minPercent : event.key === 'End' ? viewLayout.maxPercent : clamp(viewLayout.readerPercent + steps[event.key], viewLayout.minPercent, viewLayout.maxPercent);
        patchLayout({ readerPercent });
      }} />}
      <section className={`unified-chat ${!layout.chat ? 'unified-desktop-hidden' : ''}`} inert={drawerOpen ? true : undefined} style={{ flexBasis: layout.reader ? `${100 - viewLayout.readerPercent}%` : '100%' }} aria-label="任务对话">
        {activeTask ? <ChatPanel key={activeTaskId} conversationId={activeTaskId}
          showHeader onCollapse={() => patchLayout({ chat: false, reader: true, mode: 'reader' })}
          starterPrompts={currentLearning?.status === 'active' ? [
            { label: learning.completionSuggested ? '完成本轮学习' : '回到学习问题', text: '', onSelect: () => learning.completionSuggested ? learning.act(activeTask, 'finish') : locateLearning(currentLearning) },
          ] : activeTask.paperIds.length ? [
            focusedPaperId || activeTask.paperIds.length === 1 ? { label: '先看懂这篇论文', text: '/精读 帮我从研究问题、方法直觉和实验结论开始读这篇论文' }
              : { label: '先选择要读的论文', text: '', onSelect: () => { patchLayout({ navigation: true }); setCompactNavigation(true); } },
            { label: '解释读不懂的内容', text: '请解释这篇论文中我读不懂的这部分：' },
            { label: '检查一个关键结论', text: '/批判 帮我检查这篇论文最重要的结论及其证据边界' },
          ] : [{ label: '解释一个概念', text: '我想了解的概念是：' }]}
          materials={activeTask.paperIds.map(id => papers.find(paper => paper.id === id) || { id })} messages={timeline}
          onSendMessage={sendMessage} onDeleteMessage={index => { const original = timeline[index]?.originalIndex; if (Number.isInteger(original)) return deleteMessage(original); }}
          onFollowupIssue={(message, issueId) => selectCritiqueIssue(message.artifactId, issueId, message)}
          onSaveToNote={index => saveMessage(timeline[index]?.originalIndex, false)} onCaptureArtifact={index => saveMessage(timeline[index]?.originalIndex)}
          onOpenArtifact={openArtifact} onJumpToSource={jumpToSource} onAbortChat={() => learning.cancel(activeTaskId)}
          isLoading={Boolean(learning.busyTasks[activeTaskId])} showLoadingIndicator={false} enableSkills
          renderMessageAfter={renderAfterMessage} currentActivity={currentActivityBar} composerContext={composerContext} focusedMaterialId={focusedPaperId} focusMessage={focusMessage} onDraftChange={setComposerDraft}
          sendLabel={submittingLearningAnswer ? '提交回答' : '发送消息'}
          inputPlaceholder={submittingLearningAnswer ? '用自己的话回答这道题…' : undefined}
          researchCapabilities={researchCapabilities}
          researchSourcePolicy={researchSourcePolicy} onResearchSourcePolicyChange={setResearchSourcePolicy}
          researchContextOptions={[...(activeTask?.notes || []).map(value => ({ id: `note:${value.id}`, title: value.title || '未命名笔记' })),
            ...(activeTask?.artifacts || []).filter(value => value.origin !== 'machine').map(value => ({ id: `artifact:${value.id}`, title: value.title || '未命名成果' }))]}
          researchContextRefs={researchContextRefs} onResearchContextRefsChange={setResearchContextRefs}
          researchBudgetProfile={researchBudgetProfile} onResearchBudgetProfileChange={setResearchBudgetProfile} />
          : <div className="unified-empty"><p>创建任务后，即可围绕论文持续讨论。</p><button type="button" onClick={() => createTask({ title: '新任务' })}>新任务</button></div>}
      </section>
      {!layout.reader && <button type="button" className="unified-restore unified-restore-reader" title="向右展开阅读区" onClick={() => patchLayout({ reader: true, mode: 'split' })} aria-label="展开阅读区"><PanelLeftOpen size={16} />阅读</button>}
      {!layout.chat && <button type="button" className="unified-restore unified-restore-chat" title="向左展开对话区" onClick={() => patchLayout({ chat: true, mode: 'split' })} aria-label="展开对话区"><PanelRightOpen size={16} />对话</button>}
    </main>
    {workspace.error && <div className="unified-error" role="alert">{workspace.error}</div>}
    {showProcessingHistory && activeTask && <div className="task-draft-backdrop" onKeyDown={event => { if (event.key === 'Escape') setShowProcessingHistory(false); }}>
      <div ref={processingDialogRef} className="task-draft-dialog theme-panel" role="dialog" aria-modal="true" aria-label="处理记录" onKeyDown={event => {
        if (event.key !== 'Tab') return;
        const controls = [...event.currentTarget.querySelectorAll('button:not(:disabled), input, select, textarea, summary, a[href]')].filter(node => !node.closest('details:not([open])') || node.tagName === 'SUMMARY');
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }}>
        <div className="unified-document-toolbar"><strong>处理记录</strong><button type="button" onClick={() => setShowProcessingHistory(false)}>关闭</button></div>
        <TaskProcessingHistory task={activeTask} records={learning.operations.records} research={research}
          queryError={learning.error && !Object.values(learning.operations.records).some(record => record.taskId === activeTaskId && record.error === learning.error) ? learning.error : ''}
          onLocateOperation={locateOperation} onLocateResearch={locateResearch} onOpenReport={openReport} {...operationControls} />
      </div>
    </div>}
    <input ref={fileInputRef} type="file" accept="application/pdf,.pdf" hidden onChange={(event) => handleUpload(event.target.files?.[0])} />
  </div>;
}
