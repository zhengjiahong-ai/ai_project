import React, { useState, useCallback,useEffect } from 'react';
import { Panel, Group, Separator } from 'react-resizable-panels';
import PdfViewer from './components/PdfViewer';
import ChatPanel from './components/ChatPanel';
import Navbar from './components/Navbar';
import PdfToolbar from './components/PdfToolbar';
import { openDB } from 'idb'; // 引入数据库库
import CriticalAnalysisPanel from './components/CriticalAnalysisPanel'; // 确认引入新组件
// import { apiService } from './services/api';

// 初始化 IndexedDB
const initDB = async () => {
  return openDB('PixiuAcademicDB', 1, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('pdfStore')) {
        db.createObjectStore('pdfStore'); // 存储 PDF Blob
      }
      if (!db.objectStoreNames.contains('historyStore')) {
        db.createObjectStore('historyStore'); // 存储 聊天历史
      }
    },
  });
};
export default function App() {
  // PDF 文件状态（存储 blob URL）
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfFileName, setPdfFileName] = useState(null);
  
  // 对话记录
  const [messages, setMessages] = useState([
    { 
      role: 'ai', 
      content: '您好！我是您的 AI 学术助手。上传论文后，我可以为您进行批判性阅读或动态解释。' 
    }
  ]);
  // --- 新增：右侧面板切换与分析状态 ---
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' 或 'analysis'
  const [analysisData, setAnalysisData] = useState(null); // 存储后端返回的分析数据
  const [isAnalyzing, setIsAnalyzing] = useState(false); // 加载状态
  const [isRestored, setIsRestored] = useState(false);
// 处理分析逻辑
// --- 逻辑 1: 页面加载时恢复数据 (刷新保护) ---
useEffect(() => {
  const restoreSession = async () => {
    try {
      // A. LocalStorage: 恢复 UI 配置
      const savedTab = localStorage.getItem('activeTab');
      if (savedTab) setActiveTab(savedTab);

      // B. IndexedDB: 恢复大体积数据
      const db = await initDB();
      const savedPdf = await db.get('pdfStore', 'currentPdf');
      const savedMessages = await db.get('historyStore', 'chatHistory');

      if (savedPdf) {
        setPdfFile(URL.createObjectURL(savedPdf.blob));
        setPdfFileName(savedPdf.name);
      }
     // 只有数据库有数据时才覆盖默认欢迎语
     if (savedMessages && savedMessages.length > 0) {
      setMessages(savedMessages);
    }
    } catch (error) {
      console.error("恢复数据失败:", error);
    }finally {
      // 重点：无论成功失败，标记“恢复流程已结束”，允许后续写入
      setIsRestored(true);
    }
  };
  
  restoreSession(); // 执行异步恢复函数
}, []);

// --- 逻辑 2: 持久化聊天历史 ---
useEffect(() => {
  // 关键改动：如果还没恢复完成，绝对不要触发保存动作
  if (!isRestored) return;

  const saveToDB = async () => {
    try {
      const db = await initDB();
      // 只有在 messages 确实有内容时才存
      if (messages.length > 0) {
        await db.put('historyStore', messages, 'chatHistory');
        localStorage.setItem('lastUpdate', Date.now().toString());
      }
    } catch (error) {
      console.error("保存失败:", error);
    }
  };

  saveToDB();
}, [messages, isRestored]); // 必须把 isRestored 也加入依赖数组
const handleStartAnalysis = useCallback(async () => {
  setIsAnalyzing(true);
  
  /* // 未来对接后端接口
  try {
    const response = await apiService.fetchCriticalAnalysis(pdfFile);
    setAnalysisData(response.data);
  } catch (e) { console.error(e); }
  */

  // 模拟后端返回数据
  setTimeout(() => {
    setAnalysisData({
      summary: "本文在实验设计上具有创新性，但在样本量控制和长短期效应对比上存在一定局限性。",
      metrics: [
        { name: '创新性', score: 85, detail: '提出了一种全新的自适应悬浮算法。' },
        { name: '严谨性', score: 62, detail: '实验组数据在边缘条件下存在 5% 的统计偏差风险。' },
        { name: '引用质量', score: 90, detail: '引用了近 3 年内 80% 的核心期刊文献。' },
        { name: '逻辑链条', score: 75, detail: '结论推导部分对负面结果的讨论略显不足。' }
      ]
    });
    setIsAnalyzing(false);
  }, 2000);
}, [pdfFile]);
  // AI 就绪状态
  const [isAiReady, setIsAiReady] = useState(true);
// 处理划词后的解释逻辑
const handleExplain = useCallback((content, role = 'user') => {
  // 1. 创建新消息对象
  const newMessage = { 
    role: role, 
    content: content,
    id: Date.now() // 加上 ID 避免 React 渲染 key 警告
  };

  // 2. 更新消息列表
  setMessages(prev => [...prev, newMessage]);

  // 3. 如果是用户发出的请求（比如划词瞬间），可以在这里触发 AI 的全局自动回复逻辑
  if (role === 'user' && content.includes('请帮我解释')) {
    setTimeout(() => {
      const autoAiMsg = {
        role: 'ai',
        content: `我已经收到了您的划词请求，正在针对该段落进行深度解析... (您也可以在左侧小窗继续追问)`,
        id: Date.now() + 1
      };
      setMessages(prev => [...prev, autoAiMsg]);
    }, 800);
  }
}, []);
  // 处理文件上传
  const handleFileUpload = useCallback(async(file) => {
    if (file && file.type === "application/pdf") {
      // 创建本地临时 URL 用于预览
      const fileUrl = URL.createObjectURL(file);
      setPdfFile(fileUrl);
      setPdfFileName(file.name);
      // 存入 IndexedDB
      const db = await initDB();
      await db.put('pdfStore', { blob: file, name: file.name }, 'currentPdf');
      // 添加 AI 欢迎消息
      setMessages(prev => [...prev, { 
        role: 'ai', 
        content: `已成功加载论文：${file.name}。我现在可以为您分析该文章了。` 
      }]);

      // TODO: 这里可以调用 API 上传文件到后端
      // apiService.uploadPdf(file).then(response => {
      //   console.log('File uploaded:', response);
      // }).catch(error => {
      //   console.error('Upload failed:', error);
      // });
      setMessages(prev => [...prev, { role: 'ai', content: `文件 ${file.name} 已安全存入本地仓。` }]);
    } else {
      alert("请上传有效的 PDF 文件");
    }
  }, []);

  // 处理发送消息
  const handleSendMessage = useCallback((message) => {
    // 添加用户消息
    setMessages(prev => [...prev, { role: 'user', content: message }]);

    // TODO: 调用 AI API
    // apiService.sendMessage(message, pdfId).then(response => {
    //   setMessages(prev => [...prev, { role: 'ai', content: response.message }]);
    // }).catch(error => {
    //   setMessages(prev => [...prev, { 
    //     role: 'ai', 
    //     content: '抱歉，处理您的请求时出现了错误。' 
    //   }]);
    // });

    // 临时模拟 AI 响应
    setTimeout(() => {
      setMessages(prev => [...prev, { 
        role: 'ai', 
        content: '这是一个模拟的 AI 响应。请连接后端 API 以获取真实的 AI 回复。' 
      }]);
    }, 1000);
  }, []);

  // 处理动态解释
  const handleDynamicExplain = useCallback(() => {
    setMessages(prev => [...prev, { 
      role: 'ai', 
      content: '动态解释功能：请在 PDF 中选择文本，我将为您解释其含义。' 
    }]);
  }, []);

  // 处理批判性阅读
  const handleCriticalReading = useCallback(() => {
    if (!pdfFile) {
      alert('请先上传 PDF 文件');
      return;
    }

    setMessages(prev => [...prev, { 
      role: 'user', 
      content: '请对这篇论文进行批判性阅读分析。' 
    }]);

    // TODO: 调用批判性阅读 API
    // apiService.criticalReading(pdfId).then(response => {
    //   setMessages(prev => [...prev, { role: 'ai', content: response.analysis }]);
    // });

    // 临时模拟响应
    setTimeout(() => {
      setMessages(prev => [...prev, { 
        role: 'ai', 
        content: '批判性阅读分析功能：请连接后端 API 以获取完整的论文分析。' 
      }]);
    }, 1000);
  }, [pdfFile]);

  return (
    <div className="flex flex-col h-screen bg-[#F8F9FA] text-slate-900 font-sans">
      {/* 顶部导航栏 */}
      {/* 1. 修改 Navbar：传入切换函数和当前状态 */}
      <Navbar 
        onFileUpload={handleFileUpload} 
        activeTab={activeTab} 
        onTabChange={setActiveTab} 
      />

      {/* 主体交互区 */}
      <main className="flex-1 overflow-hidden">
        <Group orientation="horizontal">
          {/* 左侧：PDF 视窗 */}
          <Panel defaultSize={65} minSize={30}>
            <div className="h-full bg-[#525659] p-4 flex flex-col relative">
              {/* 新增：显示文件名，解决 pdfFileName 未使用的警告 */}
                {pdfFileName && (
                  <div className="mb-2 text-white text-sm font-medium truncate bg-black/20 px-3 py-1 rounded">
                    📄 {pdfFileName}
                  </div>
                )}
              <div className="flex-1 bg-white rounded shadow-2xl overflow-hidden">
                <PdfViewer fileUrl={pdfFile} 
                onSelection={handleExplain}
                />
              </div>
              
              {/* 悬浮工具栏 */}
              {pdfFile && (
                <PdfToolbar 
                  onDynamicExplain={handleDynamicExplain}
                  onCriticalReading={handleCriticalReading}
                />
              )}
            </div>
          </Panel>

          {/* 拖拽手柄 */}
          <Separator className="w-1.5 group transition-all hover:bg-blue-100 relative">
            <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-[2px] bg-slate-200 group-hover:bg-blue-400 transition-colors"></div>
          </Separator>

          {/* 右侧：AI 对话面板 */}
          <Panel defaultSize={35} minSize={20}>
            {/* 2. 修改右侧面板：根据 activeTab 实时切换 */}
            <div className="h-full bg-white flex flex-col">
              {activeTab === 'chat' ? (
                <ChatPanel 
                  messages={messages}
                  onSendMessage={handleSendMessage}
                />
              ) : (
                <CriticalAnalysisPanel 
                  data={analysisData} 
                  onAnalyze={handleStartAnalysis} 
                  isLoading={isAnalyzing}
                />
              )}
            </div>
          </Panel>
        </Group>
      </main>
    </div>
  );
}
