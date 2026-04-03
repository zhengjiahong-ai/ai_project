import React, { useState, useCallback, useEffect } from 'react';
import { Panel, Group, Separator } from 'react-resizable-panels';
import { Trash2 } from 'lucide-react';
import PdfViewer from './components/PdfViewer';
import ChatPanel from './components/ChatPanel';
import Navbar from './components/Navbar';
import PdfToolbar from './components/PdfToolbar';
import { openDB } from 'idb';
import ReactMarkdown from 'react-markdown';
import CriticalAnalysisPanel from './components/CriticalAnalysisPanel';
import { apiService } from './services/api';
import PaperAnalysis from './components/PaperAnalysis';
import SocraticQuestionsPanel from './components/SocraticQuestionsPanel';
import LibrarySidebar from './components/LibrarySidebar';

const initDB = async () => {
  return openDB('PixiuAcademicDB_v6', 2, {
    upgrade(db, oldVersion, newVersion, transaction) {
      if (!db.objectStoreNames.contains('pdfStore')) db.createObjectStore('pdfStore'); 
      if (!db.objectStoreNames.contains('historyStore')) db.createObjectStore('historyStore'); 
      if (!db.objectStoreNames.contains('analysisStore')) db.createObjectStore('analysisStore');
      if (!db.objectStoreNames.contains('notesStore')) db.createObjectStore('notesStore'); 
      if (!db.objectStoreNames.contains('deconstructStore')) db.createObjectStore('deconstructStore');
      if (!db.objectStoreNames.contains('libraryStore')) db.createObjectStore('libraryStore', { keyPath: 'id' });
      if (!db.objectStoreNames.contains('highlightStore')) db.createObjectStore('highlightStore');
    },
  });
};
export default function App() {
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfFileName, setPdfFileName] = useState(null);
  const [pdfId, setPdfId] = useState(null);
  const [isAiReady, setIsAiReady] = useState(true);
  const [messages, setMessages] = useState([
    { 
      role: 'ai', 
      content: '您好！我是您的 AI 学术助手。上传论文后，您可以直接**划选正文句子**进行深度解释，或在右侧进行批判性问答。' 
    }
  ]);
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
  const abortControllers = React.useRef({});
  
  const [papersList, setPapersList] = useState([]);
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);

const handlePdfUpload = async (file) => {
  if (!file) return;

  setPdfFileName(file.name);
  const fileUrl = URL.createObjectURL(file);
  setPdfFile(fileUrl);
  
  setIsAiReady(false);
  setIsDeconstructing(true);
  try {
    const response = await apiService.uploadPdf(file);
    
    console.log("后端响应结果:", response);
    if (response && response.status === "success") {
      setDeconstructData(response);
      setPdfId(response.pdfId);
      setActiveTab('deconstruct');
      const db = await initDB();
      await db.put('pdfStore', file, response.pdfId);
      await db.put('deconstructStore', response, response.pdfId);
      
      const newEntry = {
        id: response.pdfId,
        filename: file.name,
        timestamp: Date.now()
      };
      await db.put('libraryStore', newEntry);

      localStorage.setItem('lastPdfId', response.pdfId);
      
      setPapersList(prev => [newEntry, ...prev.filter(p => p.id !== response.pdfId)]);
      
      setMessages([{ role: 'ai', content: `已成功加载论文：${file.name}。我现在可以为您分析该文章了。` }]);
      setNotes([]);
      setAnalysisData(null);
    }
    setIsAiReady(true);
  } catch (error) {
    console.error("上传至后端失败:", error);
    alert("上传失败，请确保 Java 后端(8080)和 Python(8000) 已启动");
  }finally {
    setIsDeconstructing(false);
  }
};

useEffect(() => {
  const restoreSession = async () => {
    try {
      const savedTab = localStorage.getItem('activeTab');
      if (savedTab) setActiveTab(savedTab);

      const db = await initDB();
      
      const list = await db.getAll('libraryStore');
      const sortedList = list.sort((a,b) => b.timestamp - a.timestamp);
      setPapersList(sortedList);

      const savedPdfId = localStorage.getItem('lastPdfId');
      if (savedPdfId) {
        const savedPdf = await db.get('pdfStore', savedPdfId);
        const savedMessages = await db.get('historyStore', savedPdfId);
        const savedAnalysis = await db.get('analysisStore', savedPdfId);
        const savedDeconstruct = await db.get('deconstructStore', savedPdfId);
        const savedNotes = await db.get('notesStore', savedPdfId);
        const savedHighlights = await db.get('highlightStore', savedPdfId);
        
        setPdfId(savedPdfId);
        if (savedPdf) {
          setPdfFile(URL.createObjectURL(savedPdf));
          const libItem = sortedList.find(p => p.id === savedPdfId);
          if (libItem) setPdfFileName(libItem.filename);
        }
        
        if (savedDeconstruct) setDeconstructData(savedDeconstruct);
        if (savedNotes) setNotes(savedNotes);
        if (savedAnalysis) setAnalysisData(savedAnalysis);
        if (savedMessages && savedMessages.length > 0) setMessages(savedMessages);
        if (savedHighlights) setPdfHighlights(savedHighlights);
      }
    } catch (error) {
      console.error("恢复数据失败:", error);
    }finally {
      setIsRestored(true);
    }
  };
  
  restoreSession();
}, []);

const handleSelectPaper = useCallback(async (targetPdfId) => {
  setIsAiReady(false);
  try {
    const db = await initDB();
    const savedPdf = await db.get('pdfStore', targetPdfId);
    if (!savedPdf) return;

    const savedMessages = await db.get('historyStore', targetPdfId);
    const savedAnalysis = await db.get('analysisStore', targetPdfId);
    const savedDeconstruct = await db.get('deconstructStore', targetPdfId);
    const savedNotes = await db.get('notesStore', targetPdfId);
    const savedHighlights = await db.get('highlightStore', targetPdfId);

    setPdfId(targetPdfId);
    setPdfFile(URL.createObjectURL(savedPdf));
    const libItem = papersList.find(p => p.id === targetPdfId);
    if (libItem) setPdfFileName(libItem.filename);
    localStorage.setItem('lastPdfId', targetPdfId);

    setDeconstructData(savedDeconstruct || null);
    setNotes(savedNotes || []);
    setAnalysisData(savedAnalysis || null);
    setMessages(savedMessages && savedMessages.length > 0 ? savedMessages : [{ role: 'ai', content: `您好！我是您的学术助手 貔貅。` }]);
    setPdfHighlights(savedHighlights || []);
  } catch (error) {
    console.error("加载指定论文失败", error);
  } finally {
    setIsAiReady(true);
  }
}, [papersList]);

const handleDeletePaper = useCallback(async (targetPdfId) => {
  if (!confirm("确定移除该论文及所有关联聊天、笔记记录吗？")) return;
  try {
    const db = await initDB();
    await db.delete('pdfStore', targetPdfId);
    await db.delete('historyStore', targetPdfId);
    await db.delete('analysisStore', targetPdfId);
    await db.delete('notesStore', targetPdfId);
    await db.delete('deconstructStore', targetPdfId);
    await db.delete('libraryStore', targetPdfId);
    await db.delete('highlightStore', targetPdfId);
    
    setPapersList(prev => prev.filter(p => p.id !== targetPdfId));
    
    if (pdfId === targetPdfId) {
      setPdfId(null);
      setPdfFile(null);
      setPdfFileName(null);
      localStorage.removeItem('lastPdfId');
      setMessages([{ role: 'ai', content: `请从左边侧边栏选择论文或重新上传。` }]);
      setNotes([]);
      setDeconstructData(null);
      setAnalysisData(null);
    }
  } catch (err) {
    console.error("删除论文失败", err);
  }
}, [pdfId]);

useEffect(() => {
  if (!isRestored || !pdfId) return;

  const saveToDB = async () => {
    try {
      const db = await initDB();
      if (messages && messages.length > 0) {
        await db.put('historyStore', messages, pdfId);
        localStorage.setItem('activeTab', activeTab);
      }
    } catch (error) {
      console.error("保存失败:", error);
    }
  };

  saveToDB();
}, [messages, activeTab, isRestored, pdfId]);

useEffect(() => {
  if (!isRestored || !pdfId) return;

  const saveNotesToDB = async () => {
    try {
      const db = await initDB();
      await db.put('notesStore', notes, pdfId);
      console.log("笔记已同步至数据库", notes);
    } catch (error) {
      console.error("笔记保存失败:", error);
    }
  };

  saveNotesToDB();
}, [notes, isRestored, pdfId]);

const handleStartAnalysis = useCallback(async () => {
  setIsAnalyzing(true);

  setTimeout(async () => {
    const mockResult = {
      summary: "本文在实验设计上具有创新性，但在样本量控制和长短期效应对比上存在一定局限性。",
      metrics: [
        { name: '创新性', score: 85, detail: '提出了一种全新的自适应悬浮算法。' },
        { name: '严谨性', score: 62, detail: '实验组数据在边缘条件下存在 5% 的统计偏差风险。' },
        { name: '引用质量', score: 90, detail: '引用了近 3 年内 80% 的核心期刊文献。' },
        { name: '逻辑链条', score: 75, detail: '结论推导部分对负面结果的讨论略显不足。' }
      ]
    };

    setAnalysisData(mockResult);
    setIsAnalyzing(false);

    try {
      if (pdfId) {
        const db = await initDB();
        await db.put('analysisStore', mockResult, pdfId);
        console.log("分析数据已持久化至本地仓", pdfId);
      }
    } catch (e) {
      console.error("持久化分析数据失败:", e);
    }
  }, 2000);
}, [pdfId]);

  const handleSendMessage = useCallback((message) => {
    if (!pdfId || loadingPapers[pdfId]) return; 

    setActiveTab('chat');
    setMessages(prev => [...prev, { role: 'user', content: message }]);
    
    const controller = new AbortController();
    abortControllers.current[pdfId] = controller;

    setLoadingPapers(prev => ({ ...prev, [pdfId]: true }));

    const skeleton = deconstructData?.paper_skeleton || null;
    const history = messages.slice(-6).map(m => ({ 
      role: m.role === 'ai' ? 'assistant' : 'user', 
      content: m.content 
    }));

    apiService.sendMessage(message, pdfId, history, skeleton, controller.signal)
      .then((response) => {
        const content = response?.data?.reply ?? response?.reply ?? response?.message ?? '暂无回复';
        setMessages(prev => [...prev, { role: 'ai', content }]);
      })
      .catch((error) => {
        if (error.name === 'CanceledError' || error.message === 'canceled') {
          console.log("对话已手动中止");
          return;
        }
        const errMsg = error?.response?.data?.message ?? error?.message ?? '请求失败，请稍后重试';
        setMessages(prev => [...prev, { role: 'ai', content: `抱歉，处理您的请求时出现了错误：${errMsg}` }]);
      })
      .finally(() => {
        setLoadingPapers(prev => ({ ...prev, [pdfId]: false }));
        delete abortControllers.current[pdfId];
      });
  }, [pdfId, loadingPapers, messages, deconstructData]);

  const handleAbortChat = useCallback((targetId) => {
    const controller = abortControllers.current[targetId];
    if (controller) {
      controller.abort();
      
      // 添加中止提示
      setMessages(prev => [...prev, { 
        role: 'ai', 
        isSystem: true,
        content: '⚠️ 本次回答已由用户取消。' 
      }]);

      setLoadingPapers(prev => ({ ...prev, [targetId]: false }));
      delete abortControllers.current[targetId];
    }
  }, []);

  const handleDeleteChatMessage = useCallback((index) => {
    setMessages(prev => {
      const targetMsg = prev[index];
      if (!targetMsg) return prev;

      const indicesToDelete = [index];
      
      if (targetMsg.role === 'user') {
        if (index + 1 < prev.length && prev[index + 1].role === 'ai') {
          indicesToDelete.push(index + 1);
        }
      } 
      else if (targetMsg.role === 'ai' && index > 0) {
        if (prev[index - 1].role === 'user') {
          indicesToDelete.push(index - 1);
        }
      }

      return prev.filter((_, i) => !indicesToDelete.includes(i));
    });
  }, []);

  const handleExplain = useCallback((content, role = 'user', isSyncOnly = false) => {
    setActiveTab('chat');
    if (role === 'user' && !isSyncOnly) {
      handleSendMessage(`请解释以下内容：${content}`);
    } else {
      setMessages(prev => [...prev, { 
        role: role, 
        content: content,
        id: Date.now() 
      }]);
    }
  }, [handleSendMessage]);
  
  const handleAddNote = useCallback((noteData) => {
    setNotes(prev => [{
      id: Date.now(),
      ...noteData,
      time: new Date().toLocaleTimeString()
    }, ...prev]);
  }, []);
  
  // 保存对话到笔记
  const handleSaveChatToNote = useCallback((index) => {
    const msg = messages[index];
    if (!msg) return;

    let question = "";
    let answer = "";

    if (msg.role === 'user') {
      question = msg.content;
      const nextMsg = messages[index + 1];
      answer = (nextMsg && nextMsg.role === 'ai') ? nextMsg.content : "等待 AI 回答中...";
    } else {
      answer = msg.content;
      const prevMsg = messages[index - 1];
      question = (prevMsg && prevMsg.role === 'user') ? prevMsg.content : "提问内容定位失败";
    }

    handleAddNote({
      text: question,
      aiInterpretation: answer,
      pageNumber: -1 // 表示来自通用对话，非 PDF 特定页码
    });
    
    alert("已将该对话内容收藏至‘学术笔记’！");
  }, [messages, handleAddNote]);

  const handleGenerateSocratic = useCallback(async (readingProgress) => {
    if (!deconstructData || !deconstructData.paper_skeleton) {
      throw new Error('请先完成“篇章解构”，系统需要论文结构内容。');
    }

    setIsSocraticLoading(true);
    try {
      const paper_content = JSON.stringify(deconstructData.paper_skeleton);
      const res = await apiService.socraticQuestions(paper_content, readingProgress);
      if (res?.status === 'success') {
        setSocraticQuestions(res.questions || []);
      } else {
        throw new Error(res?.message || '生成失败');
      }
    } finally {
      setIsSocraticLoading(false);
    }
  }, [deconstructData]);

  const handleDynamicExplain = useCallback(() => {
    setActiveTab('chat');
    setMessages(prev => [...prev, { 
      role: 'ai', 
      content: '💡 **功能提示**：在左侧 PDF 视窗中直接**鼠标划选**任何不理解的句子或段落，点击弹出的“AI 解释”按钮，我将结合整篇论文上下文为您深度解析。' 
    }]);
  }, []);

  const handleCriticalReading = useCallback(() => {
    if (!pdfFile) {
      alert('请先上传 PDF 文件');
      return;
    }

    setMessages(prev => [...prev, { 
      role: 'user', 
      content: '请对这篇论文进行批判性阅读分析。' 
    }]);

    setTimeout(() => {
      setMessages(prev => [...prev, { 
        role: 'ai', 
        content: '批判性阅读分析功能：请连接后端 API 以获取完整的论文分析。' 
      }]);
    }, 1000);
  }, [pdfFile]);


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
    <div className="flex flex-col h-screen bg-[#F8F9FA] text-slate-900 font-sans">
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
            <div className="h-full bg-[#525659] p-4 flex flex-col relative">
                {pdfFileName && (
                  <div className="mb-2 text-white text-sm font-medium truncate bg-black/20 px-3 py-1 rounded">
                    <span>📄 {pdfFileName}</span>
                  {isTranslated && <span className="text-pixiu animate-pulse text-xs">智能双语图层已开启</span>}
                  </div>
                )}
              <div className="flex-1 bg-white rounded shadow-2xl overflow-hidden">
                <PdfViewer 
                  fileUrl={pdfFile} 
                  pdfId={pdfId}
                  onSelection={handleExplain}
                  onSaveNote={handleAddNote}
                  isTranslated={isTranslated}
                  initialHighlights={pdfHighlights}
                  onHighlightsChange={(newHighlights) => {
                    setPdfHighlights(newHighlights);
                    initDB().then(db => {
                      if (pdfId) db.put('highlightStore', newHighlights, pdfId);
                    });
                  }}
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
                  onToggleTranslation={() => setIsTranslated(!isTranslated)}
                />
              )}
            </div>
          </Panel>

          <Separator className="w-1.5 group transition-all hover:bg-pixiu/10 relative">
            <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-[2px] bg-slate-200 group-hover:bg-pixiu/40 transition-colors"></div>
          </Separator>

          <Panel defaultSize={35}>
            <div className="h-full bg-white flex flex-col">
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
                <CriticalAnalysisPanel data={analysisData} onAnalyze={handleStartAnalysis} isLoading={isAnalyzing} />
              )}
              {activeTab === 'notes' && (
                <div className="flex-1 flex flex-col bg-slate-50 overflow-hidden">
                  <div className="p-4 border-b bg-white font-bold text-pixiu">📌 学术笔记精华</div>
                  <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {notes.map(note => (
                      <div key={note.id} className="relative group bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                        <button 
                          onClick={() => {
                            if (window.confirm("确定删除这条学术笔记吗？")) {
                              setNotes(prev => prev.filter(n => n.id !== note.id));
                            }
                          }}
                          className="absolute top-2 right-2 p-1.5 opacity-0 group-hover:opacity-100 transition-opacity rounded-md bg-red-50 text-red-500 hover:bg-red-100"
                          title="删除此笔记"
                        >
                          <Trash2 size={14} />
                        </button>

                        <div className="flex justify-between text-[10px] text-pixiu font-bold mb-2">
                          <span>PAGE {note.pageNumber + 1}</span>
                          <span>{note.time}</span>
                        </div>
                        <p className="text-sm italic text-slate-500 border-l-2 border-slate-200 pl-3 mb-3">"{note.text}"</p>
                        <div className="text-sm bg-pixiu/5 p-3 rounded-lg prose prose-sm prose-slate max-w-none">
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
