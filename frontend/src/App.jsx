import React, { useState, useCallback } from 'react';
import { Panel, Group, Separator } from 'react-resizable-panels';
import PdfViewer from './components/PdfViewer';
import ChatPanel from './components/ChatPanel';
import Navbar from './components/Navbar';
import PdfToolbar from './components/PdfToolbar';
// import { apiService } from './services/api';

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

  // AI 就绪状态
  const [isAiReady, setIsAiReady] = useState(true);
// 处理划词后的解释逻辑
const handleExplain = (text) => {
  // 1. 自动滚动到 AI 面板并展示“思考中”状态
  const userMsg = { role: 'user', content: `请解释这段文字：${text}` };
  setMessages(prev => [...prev, userMsg]);
  
  // 2. 模拟 AI 响应 (将来替换为 Axios 请求)
  setTimeout(() => {
    const aiMsg = { 
      role: 'ai', 
      content: `### 动态解释 \n\n 这段话的核心意思是：**${text.substring(0, 20)}...** \n\n 这里的专业术语可以理解为...` 
    };
    setMessages(prev => [...prev, aiMsg]);
  }, 1000);
};
  // 处理文件上传
  const handleFileUpload = useCallback((file) => {
    if (file && file.type === "application/pdf") {
      // 创建本地临时 URL 用于预览
      const fileUrl = URL.createObjectURL(file);
      setPdfFile(fileUrl);
      setPdfFileName(file.name);
      
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
      <Navbar onFileUpload={handleFileUpload} isReady={isAiReady} />

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
            <ChatPanel 
              messages={messages}
              onSendMessage={handleSendMessage}
            />
          </Panel>
        </Group>
      </main>
    </div>
  );
}
