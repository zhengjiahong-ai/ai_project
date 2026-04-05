import React, { useCallback, useEffect, useRef, useState } from 'react';
import { openDB } from 'idb';
import { Trash2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Group, Panel, Separator } from 'react-resizable-panels';

import ChatPanel from './components/ChatPanel';
import CriticalAnalysisPanel from './components/CriticalAnalysisPanel';
import LibrarySidebar from './components/LibrarySidebar';
import Navbar from './components/Navbar';
import PaperAnalysis from './components/PaperAnalysis';
import PdfToolbar from './components/PdfToolbar';
import PdfViewer from './components/PdfViewer';
import SocraticQuestionsPanel from './components/SocraticQuestionsPanel';
import { apiService } from './services/api';

const WELCOME_MESSAGE = {
  role: 'ai',
  content: '您好！我是您的 AI 学术助手。上传论文后，您可以直接划选正文句子进行解释、批判阅读，并保留对话历史。',
};

const SOCRATIC_TOTAL_QUESTIONS = 5;

const initDB = async () =>
  openDB('PixiuAcademicDB_v6', 3, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('pdfStore')) db.createObjectStore('pdfStore');
      if (!db.objectStoreNames.contains('historyStore')) db.createObjectStore('historyStore');
      if (!db.objectStoreNames.contains('analysisStore')) db.createObjectStore('analysisStore');
      if (!db.objectStoreNames.contains('notesStore')) db.createObjectStore('notesStore');
      if (!db.objectStoreNames.contains('deconstructStore')) db.createObjectStore('deconstructStore');
      if (!db.objectStoreNames.contains('libraryStore')) db.createObjectStore('libraryStore', { keyPath: 'id' });
      if (!db.objectStoreNames.contains('highlightStore')) db.createObjectStore('highlightStore');
      if (!db.objectStoreNames.contains('sessionStore')) db.createObjectStore('sessionStore');
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

const createEmptySocraticSession = (pdfId = null, overrides = {}) => ({
  pdfId,
  started: false,
  readingProgress: '',
  intro: '',
  totalQuestions: SOCRATIC_TOTAL_QUESTIONS,
  currentIndex: 1,
  currentQuestion: '',
  turns: [],
  finalSummary: '',
  isComplete: false,
  updatedAt: null,
  ...overrides,
});

const normalizeSocraticSession = (storedValue, pdfId = null) => {
  if (!storedValue) {
    return createEmptySocraticSession(pdfId);
  }

  const turns = Array.isArray(storedValue.turns)
    ? storedValue.turns
        .map((turn, index) => ({
          index: Number(turn?.index) || index + 1,
          question: turn?.question || '',
          answer: turn?.answer || '',
          masteryLevel: turn?.masteryLevel || '一般',
          feedback: turn?.feedback || '',
          hint: turn?.hint || '',
        }))
        .filter((turn) => turn.question && turn.answer)
    : [];

  const totalQuestions = Number(storedValue.totalQuestions) || SOCRATIC_TOTAL_QUESTIONS;
  const isComplete = Boolean(storedValue.isComplete);
  const inferredCurrentIndex = Math.min(turns.length + 1, totalQuestions);
  const currentIndex = isComplete
    ? totalQuestions
    : Math.max(1, Math.min(Number(storedValue.currentIndex) || inferredCurrentIndex, totalQuestions));

  return createEmptySocraticSession(pdfId ?? storedValue.pdfId ?? null, {
    started: Boolean(storedValue.started || turns.length > 0 || storedValue.currentQuestion || isComplete),
    readingProgress: storedValue.readingProgress || '',
    intro: storedValue.intro || '',
    totalQuestions,
    currentIndex,
    currentQuestion: isComplete ? '' : storedValue.currentQuestion || '',
    turns,
    finalSummary: storedValue.finalSummary || '',
    isComplete,
    updatedAt: storedValue.updatedAt || null,
  });
};

export default function App() {
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfFileName, setPdfFileName] = useState(null);
  const [pdfId, setPdfId] = useState(null);
  const [isAiReady, setIsAiReady] = useState(true);
  const [messages, setMessages] = useState([WELCOME_MESSAGE]);
  const [activeTab, setActiveTab] = useState('chat');
  const [analysisData, setAnalysisData] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isRestored, setIsRestored] = useState(false);
  const [notes, setNotes] = useState([]);
  const [isTranslated, setIsTranslated] = useState(false);
  const [isDeconstructing, setIsDeconstructing] = useState(false);
  const [deconstructData, setDeconstructData] = useState(null);
  const [socraticSession, setSocraticSession] = useState(createEmptySocraticSession());
  const [isSocraticLoading, setIsSocraticLoading] = useState(false);
  const [loadingPapers, setLoadingPapers] = useState({});
  const [pdfHighlights, setPdfHighlights] = useState([]);
  const [papersList, setPapersList] = useState([]);
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);

  const abortControllers = useRef({});
  const papersListRef = useRef([]);

  useEffect(() => {
    papersListRef.current = papersList;
  }, [papersList]);

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
    const [savedPdf, savedMessages, savedAnalysis, savedDeconstruct, savedNotes, savedHighlights, savedSocraticSession] = await Promise.all([
      db.get('pdfStore', targetPdfId),
      db.get('historyStore', targetPdfId),
      db.get('analysisStore', targetPdfId),
      db.get('deconstructStore', targetPdfId),
      db.get('notesStore', targetPdfId),
      db.get('highlightStore', targetPdfId),
      db.get('sessionStore', targetPdfId),
    ]);

    const resolvedPdf = resolveStoredPdfRecord(savedPdf);
    if (!resolvedPdf) {
      return false;
    }

    const currentEntries = Array.isArray(entryList) ? entryList : papersListRef.current;
    const libraryEntry = currentEntries.find((paper) => paper.id === targetPdfId);
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
    setMessages(nextMessages);
    setPdfHighlights(savedHighlights || []);
    setSocraticSession(normalizeSocraticSession(savedSocraticSession, targetPdfId));
    localStorage.setItem('lastPdfId', targetPdfId);

    return true;
  }, [fetchRemoteHistory]);

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
        filename: file.name,
        timestamp: Date.now(),
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
      ]);

      setPdfId(response.pdfId);
      setDeconstructData(response);
      setAnalysisData(null);
      setNotes([]);
      setMessages(readyMessages);
      setPdfHighlights([]);
      setSocraticSession(createEmptySocraticSession(response.pdfId));
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
      window.alert(error?.response?.data?.message || error?.message || '上传失败，请确认后端服务已启动。');
    } finally {
      setIsAiReady(true);
      setIsDeconstructing(false);
    }
  }, []);

  useEffect(() => {
    const restoreSession = async () => {
      try {
        const savedTab = localStorage.getItem('activeTab');
        if (savedTab) {
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
      ]);

      setPapersList((prev) => prev.filter((paper) => paper.id !== targetPdfId));

      if (pdfId === targetPdfId) {
        setPdfId(null);
        setPdfFile(null);
        setPdfFileName(null);
        setMessages([WELCOME_MESSAGE]);
        setNotes([]);
        setDeconstructData(null);
        setAnalysisData(null);
        setPdfHighlights([]);
        setSocraticSession(createEmptySocraticSession());
        localStorage.removeItem('lastPdfId');
      }
    } catch (error) {
      console.error('Failed to delete paper.', error);
    }
  }, [pdfId]);

  useEffect(() => {
    if (!isRestored || !pdfId) return;

    const saveMessages = async () => {
      try {
        const db = await initDB();
        if (messages && messages.length > 0) {
          await db.put('historyStore', messages, pdfId);
          localStorage.setItem('activeTab', activeTab);
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

  return (
    <>
      <LibrarySidebar
        isOpen={isLibraryOpen}
        onClose={() => setIsLibraryOpen(false)}
        papers={papersList}
        currentPdfId={pdfId}
        onSelectPaper={handleSelectPaper}
        onDeletePaper={handleDeletePaper}
      />

      <div className="flex h-screen flex-col bg-[#F8F9FA] font-sans text-slate-900">
        <Navbar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          isReady={isAiReady}
          onFileUpload={handlePdfUpload}
          onToggleLibrary={() => setIsLibraryOpen(true)}
        />

        <main className="flex-1 overflow-hidden">
          <Group orientation="horizontal">
            <Panel defaultSize={65} minSize={30}>
              <div className="relative flex h-full flex-col bg-[#525659] p-4">
                {pdfFileName && (
                  <div className="mb-2 flex items-center justify-between truncate rounded bg-black/20 px-3 py-1 text-sm font-medium text-white">
                    <span>📄 {pdfFileName}</span>
                    {isTranslated && <span className="text-xs text-pixiu">智能双语图层已开启</span>}
                  </div>
                )}

                <div className="flex-1 overflow-hidden rounded bg-white shadow-2xl">
                  <PdfViewer
                    fileUrl={pdfFile}
                    pdfId={pdfId}
                    onSelection={handleExplain}
                    onSaveNote={handleAddNote}
                    isTranslated={isTranslated}
                    initialHighlights={pdfHighlights}
                    onHighlightsChange={handleHighlightsChange}
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
                    onToggleTranslation={() => setIsTranslated((prev) => !prev)}
                  />
                )}
              </div>
            </Panel>

            <Separator className="group relative w-1.5 transition-all hover:bg-pixiu/10">
              <div className="absolute inset-y-0 left-1/2 w-[2px] -translate-x-1/2 bg-slate-200 transition-colors group-hover:bg-pixiu/40" />
            </Separator>

            <Panel defaultSize={35}>
              <div className="flex h-full flex-col bg-white">
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

                {activeTab === 'notes' && (
                  <div className="flex flex-1 flex-col overflow-hidden bg-slate-50">
                    <div className="border-b bg-white p-4 font-bold text-pixiu">📝 学术笔记精华</div>
                    <div className="flex-1 space-y-4 overflow-y-auto p-4">
                      {notes.map((note) => (
                        <div
                          key={note.id}
                          className="group relative rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
                        >
                          <button
                            onClick={() => {
                              if (window.confirm('确定删除这条学术笔记吗？')) {
                                setNotes((prev) => prev.filter((item) => item.id !== note.id));
                              }
                            }}
                            className="absolute right-2 top-2 rounded-md bg-red-50 p-1.5 text-red-500 opacity-0 transition-opacity hover:bg-red-100 group-hover:opacity-100"
                            title="删除此笔记"
                          >
                            <Trash2 size={14} />
                          </button>

                          <div className="mb-2 flex justify-between text-[10px] font-bold text-pixiu">
                            <span>PAGE {note.pageNumber + 1}</span>
                            <span>{note.time}</span>
                          </div>
                          <p className="mb-3 border-l-2 border-slate-200 pl-3 text-sm italic text-slate-500">
                            "{note.text}"
                          </p>
                          <div className="prose prose-sm max-w-none rounded-lg bg-pixiu/5 p-3 prose-slate">
                            <ReactMarkdown>{note.aiInterpretation}</ReactMarkdown>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Panel>
          </Group>
        </main>
      </div>
    </>
  );
}
