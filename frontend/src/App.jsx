import React, { useCallback, useEffect, useState, useRef } from 'react';
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
  content: '请先上传论文。我会结合论文内容帮你提问、解释术语、批判阅读，并保留对话历史。',
};

const initDB = async () =>
  openDB('PixiuAcademicDB_v6', 2, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('pdfStore')) db.createObjectStore('pdfStore');
      if (!db.objectStoreNames.contains('historyStore')) db.createObjectStore('historyStore');
      if (!db.objectStoreNames.contains('analysisStore')) db.createObjectStore('analysisStore');
      if (!db.objectStoreNames.contains('notesStore')) db.createObjectStore('notesStore');
      if (!db.objectStoreNames.contains('deconstructStore')) db.createObjectStore('deconstructStore');
      if (!db.objectStoreNames.contains('libraryStore')) db.createObjectStore('libraryStore', { keyPath: 'id' });
      if (!db.objectStoreNames.contains('highlightStore')) db.createObjectStore('highlightStore');
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
    content: `已载入《${filename}》。你可以继续提问、运行批判阅读，或生成苏格拉底式追问。`,
  },
];


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
  const [socraticQuestions, setSocraticQuestions] = useState([]);
  const [isSocraticLoading, setIsSocraticLoading] = useState(false);
  const [loadingPapers, setLoadingPapers] = useState({});
  const [pdfHighlights, setPdfHighlights] = useState([]);
  const [papersList, setPapersList] = useState([]);
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);

  const abortControllers = useRef({});

  const fetchChatHistory = useCallback(async (sessionId, fallbackMessages = []) => {
    try {
      const response = await apiService.getChatHistory(sessionId);
      const remoteMessages = normalizeHistoryMessages(response?.messages || []);
      if (remoteMessages.length > 0) {
        const db = await initDB();
        await db.put('historyStore', remoteMessages, sessionId);
        return remoteMessages;
      }
    } catch (error) {
      console.warn('Failed to load remote chat history, falling back to local cache.', error);
    }

    return fallbackMessages.length > 0 ? normalizeHistoryMessages(fallbackMessages) : [WELCOME_MESSAGE];
  }, []);

  const loadPaperState = useCallback(
    async (targetPdfId, entries = papersList) => {
      const db = await initDB();
      const [savedPdf, savedMessages, savedAnalysis, savedDeconstruct, savedNotes, savedHighlights] = await Promise.all([
        db.get('pdfStore', targetPdfId),
        db.get('historyStore', targetPdfId),
        db.get('analysisStore', targetPdfId),
        db.get('deconstructStore', targetPdfId),
        db.get('notesStore', targetPdfId),
        db.get('highlightStore', targetPdfId),
      ]);

      if (!savedPdf) {
        return false;
      }

      const entryList = Array.isArray(entries) ? entries : papersList;
      const libraryEntry = entryList.find((paper) => paper.id === targetPdfId);
      const nextMessages = await fetchChatHistory(
        targetPdfId,
        savedMessages || (libraryEntry ? createReadyMessage(libraryEntry.filename) : [WELCOME_MESSAGE]),
      );

      setPdfId(targetPdfId);
      setPdfFile(URL.createObjectURL(savedPdf));
      setPdfFileName(libraryEntry?.filename ?? savedPdf.name ?? null);
      setDeconstructData(savedDeconstruct || null);
      setNotes(savedNotes || []);
      setAnalysisData(savedAnalysis || null);
      setMessages(nextMessages);
      setPdfHighlights(savedHighlights || []);
      localStorage.setItem('lastPdfId', targetPdfId);

      return true;
    },
    [fetchChatHistory, papersList],
  );

  const handlePdfUpload = useCallback(async (file) => {
    if (!file) return;

    setPdfFileName(file.name);
    setPdfFile(URL.createObjectURL(file));
    setIsAiReady(false);
    setIsDeconstructing(true);

    try {
      const response = await apiService.uploadPdf(file);
      if (response?.status !== 'success') {
        throw new Error(response?.message || '论文上传失败');
      }

      const db = await initDB();
      const newEntry = {
        id: response.pdfId,
        filename: file.name,
        timestamp: Date.now(),
      };

      await Promise.all([
        db.put('pdfStore', file, response.pdfId),
        db.put('deconstructStore', response, response.pdfId),
        db.put('analysisStore', null, response.pdfId),
        db.put('historyStore', createReadyMessage(file.name), response.pdfId),
        db.put('libraryStore', newEntry),
      ]);

      setPdfId(response.pdfId);
      setDeconstructData(response);
      setAnalysisData(null);
      setNotes([]);
      setMessages(createReadyMessage(file.name));
      setPdfHighlights([]);
      setActiveTab('deconstruct');
      setPapersList((prev) => [newEntry, ...prev.filter((paper) => paper.id !== response.pdfId)]);
      localStorage.setItem('lastPdfId', response.pdfId);
    } catch (error) {
      console.error('Failed to upload PDF.', error);
      window.alert(error?.response?.data?.message || error?.message || '上传失败，请检查后端服务是否可用。');
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
        const sortedList = list.sort((left, right) => right.timestamp - left.timestamp);
        setPapersList(sortedList);

        const savedPdfId = localStorage.getItem('lastPdfId');
        if (savedPdfId) {
          await loadPaperState(savedPdfId, sortedList);
        }
      } catch (error) {
        console.error('Failed to restore local session.', error);
      } finally {
        setIsRestored(true);
      }
    };

    restoreSession();
  }, [loadPaperState]);

  const handleSelectPaper = useCallback(
    async (targetPdfId) => {
      setIsAiReady(false);
      try {
        await loadPaperState(targetPdfId);
      } catch (error) {
        console.error('Failed to load paper session.', error);
      } finally {
        setIsAiReady(true);
      }
    },
    [loadPaperState],
  );

  const handleDeletePaper = useCallback(
    async (targetPdfId) => {
      if (!window.confirm('确认删除这篇论文及其本地缓存内容吗？')) return;

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
          localStorage.removeItem('lastPdfId');
        }
      } catch (error) {
        console.error('Failed to delete paper.', error);
      }
    },
    [pdfId],
  );

  useEffect(() => {
    if (!isRestored || !pdfId) return;

    const saveMessages = async () => {
      try {
        const db = await initDB();
        await db.put('historyStore', messages, pdfId);
        localStorage.setItem('activeTab', activeTab);
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

  const handleStartAnalysis = useCallback(async () => {
    if (!pdfId) {
      window.alert('请先上传论文。');
      return;
    }

    setActiveTab('analysis');
    setIsAnalyzing(true);

    try {
      const response = await apiService.criticalReading(pdfId);
      const payload = response?.analysis ?? response;
      const isSuccess = response?.status === 'success' || payload?.status === 'success';
      if (!isSuccess) {
        throw new Error(response?.message || payload?.message || '批判性阅读失败');
      }

      const db = await initDB();
      setAnalysisData(payload);
      await db.put('analysisStore', payload, pdfId);
    } catch (error) {
      console.error('Failed to analyze paper critically.', error);
      window.alert(error?.response?.data?.message || error?.message || '批判性阅读失败。');
    } finally {
      setIsAnalyzing(false);
    }
  }, [pdfId]);

  const handleSendMessage = useCallback(
    (message) => {
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
          const content = response?.reply ?? response?.message ?? '暂无回复。';
          setMessages((prev) => [...prev, { role: 'ai', content }]);
        })
        .catch((error) => {
          if (error.name === 'CanceledError' || error.message === 'canceled') {
            return;
          }

          const errMsg = error?.response?.data?.message ?? error?.message ?? '请求失败，请稍后重试。';
          setMessages((prev) => [...prev, { role: 'ai', content: `处理请求时出现错误：${errMsg}` }]);
        })
        .finally(() => {
          setLoadingPapers((prev) => ({ ...prev, [pdfId]: false }));
          delete abortControllers.current[pdfId];
        });
    },
    [deconstructData, loadingPapers, messages, pdfId],
  );

  const handleAbortChat = useCallback((targetPdfId) => {
    const controller = abortControllers.current[targetPdfId];
    if (!controller) return;

    controller.abort();
    setLoadingPapers((prev) => ({ ...prev, [targetPdfId]: false }));
    setMessages((prev) => [...prev, { role: 'ai', isSystem: true, content: '本次回答已停止。' }]);
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

  const handleExplain = useCallback(
    (content, role = 'user', isSyncOnly = false) => {
      setActiveTab('chat');
      if (role === 'user' && !isSyncOnly) {
        handleSendMessage(`请解释以下内容：${content}`);
        return;
      }

      setMessages((prev) => [...prev, { role, content, id: Date.now() }]);
    },
    [handleSendMessage],
  );

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

  const handleSaveChatToNote = useCallback(
    (index) => {
      const current = messages[index];
      if (!current) return;

      const next = messages[index + 1];
      const previous = messages[index - 1];

      const question =
        current.role === 'user'
          ? current.content
          : previous?.role === 'user'
            ? previous.content
            : '未找到对应问题';
      const answer =
        current.role === 'ai'
          ? current.content
          : next?.role === 'ai'
            ? next.content
            : '等待 AI 回复中。';

      handleAddNote({
        text: question,
        aiInterpretation: answer,
        pageNumber: -1,
      });

      window.alert('已保存到学术笔记。');
    },
    [handleAddNote, messages],
  );

  const handleGenerateSocratic = useCallback(
    async (readingProgress) => {
      if (!deconstructData?.paper_skeleton) {
        throw new Error('请先完成论文解析，再生成引导问题。');
      }

      setIsSocraticLoading(true);
      try {
        const response = await apiService.socraticQuestions(
          JSON.stringify(deconstructData.paper_skeleton),
          readingProgress,
        );

        if (response?.status !== 'success') {
          throw new Error(response?.message || '生成失败');
        }

        setSocraticQuestions(response.questions || []);
      } finally {
        setIsSocraticLoading(false);
      }
    },
    [deconstructData],
  );

  const handleDynamicExplain = useCallback(() => {
    setActiveTab('chat');
    setMessages((prev) => [
      ...prev,
      {
        role: 'ai',
        content: '在左侧 PDF 中选中文本即可发起术语解释，我会结合当前论文上下文回答。',
      },
    ]);
  }, []);

  const handleHighlightsChange = useCallback(
    (nextHighlights) => {
      setPdfHighlights(nextHighlights);
      initDB().then((db) => {
        if (pdfId) {
          db.put('highlightStore', nextHighlights, pdfId);
        }
      });
    },
    [pdfId],
  );

  const handleCriticalReading = useCallback(() => {
    if (!pdfId) {
      window.alert('请先上传论文。');
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
                  <div className="mb-2 truncate rounded bg-black/20 px-3 py-1 text-sm font-medium text-white">
                    <span>当前论文：{pdfFileName}</span>
                    {isTranslated && <span className="ml-2 text-xs text-pixiu">翻译图层已开启</span>}
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
                      setSocraticQuestions([]);
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
                    isChatLoading={!!loadingPapers[pdfId]}
                    questions={socraticQuestions}
                    onGenerate={handleGenerateSocratic}
                    onAskQuestion={handleSendMessage}
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
                    <div className="border-b bg-white p-4 font-bold text-pixiu">学术笔记</div>
                    <div className="flex-1 space-y-4 overflow-y-auto p-4">
                      {notes.map((note) => (
                        <div
                          key={note.id}
                          className="group relative rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
                        >
                          <button
                            onClick={() => {
                              if (window.confirm('确认删除这条笔记吗？')) {
                                setNotes((prev) => prev.filter((item) => item.id !== note.id));
                              }
                            }}
                            className="absolute right-2 top-2 rounded-md bg-red-50 p-1.5 text-red-500 opacity-0 transition-opacity hover:bg-red-100 group-hover:opacity-100"
                            title="删除笔记"
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
