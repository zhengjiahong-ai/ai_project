import React, { useState } from 'react';
import { Worker, Viewer } from '@react-pdf-viewer/core';
import { defaultLayoutPlugin } from '@react-pdf-viewer/default-layout';
import { highlightPlugin } from '@react-pdf-viewer/highlight';
import { Sparkles, X, Send } from 'lucide-react'; 
import ReactMarkdown from 'react-markdown';

// 样式引入
import '@react-pdf-viewer/core/lib/styles/index.css';
import '@react-pdf-viewer/default-layout/lib/styles/index.css';
import '@react-pdf-viewer/highlight/lib/styles/index.css';

// --- 新增：解释弹窗组件定义 ---
// 放在 PdfViewer 外部，解决 "is not defined" 导致的白屏
const ExplanationPopup = ({ text, position, onClose, onMessageSync }) => {
  const [query, setQuery] = useState('');
  // 1. 新增：悬浮窗内部的消息历史状态，用于窗内更新
  const [chatHistory, setChatHistory] = useState([
    { role: 'ai', content: `**选中文本：** \n > ${text.substring(0, 100)}... \n\n **AI 解析中...**` }
  ]);

  const handleSubAsk = async () => {
    if (!query.trim()) return;
    
    const userQuery = query;
    setQuery('');

    // 2. 更新窗内状态 (用户追问)
    setChatHistory(prev => [...prev, { role: 'user', content: userQuery }]);

    // 3. 同步到右侧对话框
    if (onMessageSync) {
      onMessageSync(userQuery, 'user');
    }

    // 模拟 AI 回复逻辑
    setTimeout(() => {
      const aiResponse = `针对您对“${text.substring(0,10)}...”的追问，我的回答是：这是为了解决自适应和同步更新问题。`;
      
      // 4. 更新窗内状态 (AI 回复)
      setChatHistory(prev => [...prev, { role: 'ai', content: aiResponse }]);
      
      // 5. 同步 AI 回复到右侧
      if (onMessageSync) {
        onMessageSync(aiResponse, 'ai');
      }
    }, 600);
  };

  return (
    <div 
      className="absolute z-[999] bg-white rounded-xl shadow-2xl border border-blue-100 flex flex-col animate-in fade-in zoom-in duration-200"
      style={{
        // 关键：使用百分比坐标定位，并确保 z-index 足够高
        top: `${position.top + position.height}%`,
        left: `${Math.min(position.left, 50)}%`, // 靠右时往左偏移，防止超出屏幕
        width: '320px',
        // 关键：高度自适应，设置最大高度配合滚动
        height: 'auto',
        maxHeight: '450px', 
        transform: 'translateY(12px)',
      }}
    >
      {/* 头部固定 */}
      <div className="flex items-center justify-between p-3 border-b bg-blue-50/50 rounded-t-xl shrink-0">
        <span className="flex items-center gap-1.5 text-blue-700 font-bold text-xs">
          <Sparkles size={14} /> AI 解释
        </span>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={16} /></button>
      </div>

      {/* 内容区：支持内部滚动 */}
      <div className="flex-1 overflow-y-auto p-4 text-sm scrollbar-thin scrollbar-thumb-slate-200 bg-white">
         <div className="prose prose-sm flex flex-col gap-4">
            {chatHistory.map((msg, index) => (
              <div key={index} className={`p-2 rounded-lg ${msg.role === 'user' ? 'bg-blue-50 border border-blue-100' : ''}`}>
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              </div>
            ))}
         </div>
      </div>

      {/* 底部输入框固定 */}
      <div className="p-3 border-t bg-slate-50 rounded-b-xl flex gap-2 shrink-0">
        <input 
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubAsk()}
          placeholder="继续追问..." 
          className="flex-1 px-2 py-1.5 text-xs border rounded-md outline-none focus:ring-2 focus:ring-blue-500/20"
        />
        <button onClick={handleSubAsk} className="text-blue-600 hover:scale-110 transition-transform">
          <Send size={14} />
        </button>
      </div>
    </div>
  );
};

// --- 主组件 ---
const PdfViewer = ({ fileUrl, onSelection }) => {
  const [activePopup, setActivePopup] = useState(null);
  const defaultLayoutPluginInstance = defaultLayoutPlugin();
  const workerUrl = `https://unpkg.com/pdfjs-dist@3.4.120/build/pdf.worker.min.js`;

  const highlightPluginInstance = highlightPlugin({
    renderHighlightTarget: (props) => (
      <div
        className="absolute z-50"
        style={{
          top: `${props.selectionRegion.top + props.selectionRegion.height}%`,
          left: `${props.selectionRegion.left}%`,
          transform: 'translateY(10px)',
        }}
      >
       {!activePopup && (
  <button
    onClick={() => {
      const selectedText = props.selectedText; // 获取选中的文本量

      // 1. 【本地联动】设置悬浮窗数据，显示左侧局部解释窗
      setActivePopup({
        text: selectedText,
        position: props.selectionRegion,
        cancel: props.cancel
      });

      // 2. 【全局同步】调用父组件传入的函数，把消息同步到右侧 ChatPanel
      if (onSelection) {
        // 我们主动构造一个用户提问的格式发送过去
        onSelection(`请帮我解释一下论文中的这段话：\n\n> ${selectedText}`);
      }
    }}
    className="bg-blue-600 text-white p-2 rounded-full shadow-lg hover:scale-110 transition-transform flex items-center gap-1"
  >
    <Sparkles size={18} />
    <span className="text-xs font-bold pr-1">AI 解释</span> 
  </button>
)}
      </div>
    ),
  });

  return (
    <div className="h-full w-full relative"> 
      {fileUrl ? (
        <Worker workerUrl={workerUrl}>
          <Viewer 
            fileUrl={fileUrl} 
            plugins={[defaultLayoutPluginInstance, highlightPluginInstance]} 
            theme="light"
          />
        </Worker>
      ) : (
        <div className="flex flex-col items-center justify-center h-full text-slate-400 bg-slate-50">
           <p>暂无预览内容</p>
        </div>
      )}

{activePopup && (
  <ExplanationPopup 
    text={activePopup.text}
    position={activePopup.position}
    onClose={() => {
      activePopup.cancel();
      setActivePopup(null);
    }}
    // --- 修改点：将子组件的追问同步到 App.jsx ---
    onMessageSync={(content, role) => {
      if (onSelection) {
        // 调用父组件传下来的函数，实现右侧同步
        onSelection(content, role); 
      }
    }}
    // 如果你之前的 ExplanationPopup 内部用的是 onAskMore 这个名字，
    // 请确保子组件内部调用的名字和这里定义的 Prop 名字一致
    onAskMore={(query) => {
      if (onSelection) {
        onSelection(query, 'user'); // 同步用户的追问
        // 这里还可以模拟一个 AI 的即时回复同步过去
        onSelection("正在针对您的追问进行深度解析...", 'ai');
      }
    }}
  />
)}
    </div>
  );
};

export default PdfViewer;