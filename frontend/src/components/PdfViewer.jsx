import React, { useState } from 'react';
import { Worker, Viewer } from '@react-pdf-viewer/core';
import { defaultLayoutPlugin } from '@react-pdf-viewer/default-layout';
import { highlightPlugin } from '@react-pdf-viewer/highlight';
import { Sparkles, X, Send, Trash2 } from 'lucide-react'; 
import ReactMarkdown from 'react-markdown';

// 样式引入
import '@react-pdf-viewer/core/lib/styles/index.css';
import '@react-pdf-viewer/default-layout/lib/styles/index.css';
import '@react-pdf-viewer/highlight/lib/styles/index.css';
import { apiService } from '../services/api';

// --- 新增：解释弹窗组件定义 ---
// 放在 PdfViewer 外部，解决 "is not defined" 导致的白屏
// --- 修改：解释弹窗组件（纯木偶组件，不再负责异步网络） ---
const ExplanationPopup = ({ highlight, onClose, onSubAsk, onDelete, onSaveNote }) => {
  const [query, setQuery] = useState('');
  
  const handleAsk = () => {
     if (!query.trim() || highlight.isLoading) return;
     onSubAsk(query);
     setQuery('');
  };

  const handleSave = () => {
    // 过滤掉第一条系统自动生成的 "请解释...："
    const historyToSave = highlight.chatHistory.slice(1);
    
    let interpretationMarkdown = "";
    if (historyToSave.length === 1 && historyToSave[0].role === 'ai') {
        // 如果没有追问，保持原样纯净存储
        interpretationMarkdown = historyToSave[0].content;
    } else if (historyToSave.length > 1) {
        // 如果有追问记录，将它们拼接成优雅的对话流格式并存下
        interpretationMarkdown = historyToSave.map(m => {
            if (m.role === 'user') return `> **我的追问**：_${m.content}_`;
            return `**AI 解答**：\n${m.content}`;
        }).join('\n\n---\n\n');
    }

    if (!interpretationMarkdown.trim()) {
        interpretationMarkdown = "解析中...";
    }

    if (onSaveNote) {
      onSaveNote({
        text: highlight.text,
        aiInterpretation: interpretationMarkdown,
        pageNumber: highlight.position.pageIndex 
      });
      alert("包含追问记录的完整笔记已收藏至‘学术笔记’栏目！");
      onClose();
    }
  };

  return (
    <div 
      className="absolute z-[999] bg-white rounded-xl shadow-2xl border border-blue-100 flex flex-col animate-in fade-in zoom-in duration-200"
      style={{
        ...(highlight.position.top > 55 
            ? { bottom: `${100 - highlight.position.top}%`, transform: 'translateY(-12px)' }
            : { top: `${highlight.position.top + highlight.position.height}%`, transform: 'translateY(12px)' }
        ),
        left: `min(${highlight.position.left}%, calc(100% - 340px))`,
        width: '320px',
        height: 'auto',
        maxHeight: '400px',
      }}
    >
      <div className="flex items-center justify-between p-3 border-b bg-blue-50/50 rounded-t-xl shrink-0">
        <span className="flex items-center gap-1.5 text-pixiu font-bold text-xs">
          <Sparkles size={14} /> AI 解释
        </span>
        <div className="flex items-center gap-2">
          {onSaveNote && (
           <button onClick={handleSave} className="text-[10px] bg-pixiu text-white px-2 py-1 rounded hover:bg-pixiu-dark transition-colors">
              存为笔记
            </button>
          )}
          {/* 删除高亮线和记录的按钮 */}
          <button onClick={onDelete} className="text-red-400 hover:text-red-600 p-1 hover:bg-red-50 rounded-full transition-colors" title="删除划线">
             <Trash2 size={14} />
          </button>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 p-1 hover:bg-slate-200/50 rounded-full transition-colors">
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 text-sm scrollbar-thin scrollbar-thumb-slate-200 bg-white">
         <div className="prose prose-sm flex flex-col gap-4">
            {highlight.chatHistory.map((msg, index) => {
              if (index === 0 && msg.role === 'user') return null; 
              return (
                <div key={index} className={`p-3 rounded-xl ${msg.role === 'user' ? 'bg-pixiu/5 border border-pixiu/10 text-slate-800' : 'bg-slate-50 text-slate-700'}`}>
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              );
            })}
            {highlight.isLoading && (
              <div className="flex items-center gap-2 p-2 text-slate-400 text-xs italic">
                 <Sparkles size={12} className="animate-pulse" /> AI 正在思考...
              </div>
            )}
         </div>
      </div>

      <div className="p-3 border-t bg-slate-50 rounded-b-xl flex gap-2 shrink-0">
        <input 
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
          placeholder="继续追问..." 
          className="flex-1 px-2 py-1.5 text-xs border rounded-md outline-none focus:ring-2 focus:ring-pixiu/20"
        />
        <button 
          onClick={handleAsk} 
          disabled={highlight.isLoading || !query.trim()}
          className="text-pixiu hover:scale-110 transition-transform disabled:opacity-50 disabled:hover:scale-100"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
};
// 1. 新增：翻译遮罩子组件 (用于模拟 Canvas/SVG 翻译效果)
const TranslationOverlay = () => (
  <div className="absolute inset-0 pointer-events-none z-10 overflow-hidden select-none">
    {/* 混合模式蒙版，营造“智能扫描”视觉感 */}
    <div className="absolute inset-0 bg-pixiu/5 mix-blend-multiply" />
    
    {/* 模拟翻译条纹：实际开发中这里可以对接 OCR 坐标和翻译后的 Text 对象 */}
    <div className="p-20 space-y-16 opacity-20">
      {[...Array(6)].map((_, i) => (
        <div key={i} className="space-y-3">
          <div className="h-3 bg-pixiu/30 rounded w-2/3 animate-pulse" />
          <div className="h-3 bg-slate-300 rounded w-full" />
          <div className="h-3 bg-pixiu/20 rounded w-1/2" />
        </div>
      ))}
    </div>

    {/* 水印标识 */}
    <div className="absolute bottom-4 right-4 bg-pixiu text-white text-[8px] px-2 py-1 rounded backdrop-blur-sm font-bold uppercase tracking-widest">
      PIXIU AI BILINGUAL ENGINE
    </div>
  </div>
);
// --- 主组件 ---
const PdfViewer = ({ fileUrl, onSelection, onSaveNote, isTranslated, pdfId, initialHighlights, onHighlightsChange }) => {
  // 全局持有的高亮块集合与激活态 ID
  const [highlights, setHighlights] = useState([]);
  const [activeHighlightId, setActiveHighlightId] = useState(null);

  const defaultLayoutPluginInstance = defaultLayoutPlugin();
  const workerUrl = `https://unpkg.com/pdfjs-dist@3.4.120/build/pdf.worker.min.js`;

  // 当切换论文时，自动关闭活跃的弹窗，并加载该论文专用的高亮数据
  React.useEffect(() => {
    setActiveHighlightId(null);
    setHighlights(initialHighlights || []);
    // 故意不再监听 initialHighlights 防止内部修改被重绘覆盖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdfId]);

  // 当高亮数据（包括被修改的对话树）发生变化时，抛出供父组件落库
  const isFirstRender = React.useRef(true);
  React.useEffect(() => {
    if (isFirstRender.current) {
        isFirstRender.current = false;
        return;
    }
    if (onHighlightsChange) {
        onHighlightsChange(highlights);
    }
  }, [highlights]);

  // --- 网络请求逻辑提升到此 --- 
  const handleInitialAsk = async (id, text) => {
    try {
        const response = await apiService.sendMessage(`请解释以下内容：\n> ${text}`, pdfId);
        const content = response?.data?.reply ?? response?.reply ?? response?.message ?? '暂无回复';
        setHighlights(prev => prev.map(h => h.id === id ? {
            ...h,
            chatHistory: [...h.chatHistory, { role: 'ai', content }],
            isLoading: false
        } : h));
        if (onSelection) {
            onSelection(content, 'ai', true);
        }
    } catch (err) {
        setHighlights(prev => prev.map(h => h.id === id ? {
            ...h,
            chatHistory: [...h.chatHistory, { role: 'ai', content: '抱歉，解析请求失败。' }],
            isLoading: false
        } : h));
    }
  };

  const handleSubAsk = async (id, query) => {
    const highlight = highlights.find(h => h.id === id);
    if (!highlight || highlight.isLoading) return;

    const newHistory = [...highlight.chatHistory, { role: 'user', content: query }];
    setHighlights(prev => prev.map(h => h.id === id ? { ...h, chatHistory: newHistory, isLoading: true } : h));

    if (onSelection) onSelection(query, 'user', true);

    try {
       const backendHistory = newHistory.slice(0, -1).map(m => ({ 
           role: m.role === 'ai' ? 'assistant' : 'user', 
           content: m.content 
       }));
       const response = await apiService.sendMessage(query, pdfId, backendHistory);
       const aiResponse = response?.data?.reply ?? response?.reply ?? response?.message ?? '暂无回复';
       
       setHighlights(prev => prev.map(h => h.id === id ? {
           ...h,
           chatHistory: [...h.chatHistory, { role: 'ai', content: aiResponse }],
           isLoading: false
       } : h));
       
       if (onSelection) onSelection(aiResponse, 'ai', true);
    } catch (err) {
       setHighlights(prev => prev.map(h => h.id === id ? {
           ...h,
           chatHistory: [...h.chatHistory, { role: 'ai', content: '抱歉，请求失败。' }],
           isLoading: false
       } : h));
    }
  };

  // 当切换论文时，自动关闭活跃的弹窗
  React.useEffect(() => {
    setActiveHighlightId(null);
  }, [pdfId]);

  const highlightPluginInstance = highlightPlugin({
    renderHighlightTarget: (props) => (
      <div
        className="absolute z-50 flex"
        style={{
          top: `${props.selectionRegion.top + props.selectionRegion.height}%`,
          left: `${props.selectionRegion.left}%`,
          transform: 'translateY(10px)',
        }}
      >
       {!activeHighlightId && (
        <button
          onClick={() => {
            const selectedText = props.selectedText;
            const id = Date.now();
            
            // 构建高亮块实体并固化
            setHighlights(prev => [...prev, {
               id,
               text: selectedText,
               highlightAreas: props.highlightAreas,
               position: props.selectionRegion,
               chatHistory: [{ role: 'user', content: `请解释以下内容：\n> ${selectedText}` }],
               isLoading: true
            }]);
            
            setActiveHighlightId(id); // 唤起对应的小窗
            props.cancel(); // 消除原生的 PDF 蓝底选区
            
            if (onSelection) onSelection(`请解释以下内容：\n> ${selectedText}`, 'user', true);
            
            // 开始异步请求
            handleInitialAsk(id, selectedText);
          }}
          className="bg-pixiu text-white p-2 rounded-full shadow-lg hover:scale-110 transition-transform flex items-center gap-1"
        >
          <Sparkles size={18} />
          <span className="text-xs font-bold pr-1">AI 解释</span> 
        </button>
      )}
      </div>
    ),
    // 这个核心渲染槽让 PDF 在页面上永久画出方块
    renderHighlights: (props) => (
      <div>
        {highlights.map((hightlightEntity) => (
          <React.Fragment key={hightlightEntity.id}>
            {hightlightEntity.highlightAreas
              .filter((area) => area.pageIndex === props.pageIndex)
              .map((area, idx) => (
                <div
                  key={idx}
                  style={Object.assign(
                    {},
                    {
                      background: activeHighlightId === hightlightEntity.id ? 'rgba(77, 0, 153, 0.4)' : 'rgba(77, 0, 153, 0.2)',
                      border: activeHighlightId === hightlightEntity.id ? '1px solid rgba(77, 0, 153, 0.6)' : 'none',
                      cursor: 'pointer',
                      mixBlendMode: 'multiply',
                      zIndex: 10, // Elevate above text layer so onClick works
                      pointerEvents: 'auto'
                    },
                    props.getCssProperties(area, props.rotation)
                  )}
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    setActiveHighlightId(hightlightEntity.id);
                  }}
                />
              ))}
          </React.Fragment>
        ))}
      </div>
    ),
  });

  return (
    <div className="h-full w-full relative"> 
    {/* 🚀 核心逻辑：当开启翻译时渲染遮罩层 */}
    {isTranslated && <TranslationOverlay />}
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

{/* 渲染当前活跃的小窗 */}
{activeHighlightId && (
  (() => {
    const activeData = highlights.find(h => h.id === activeHighlightId);
    if (!activeData) return null;
    return (
      <ExplanationPopup 
        highlight={activeData}
        onClose={() => setActiveHighlightId(null)}
        onSubAsk={(query) => handleSubAsk(activeData.id, query)}
        onDelete={() => {
          setHighlights(prev => prev.filter(h => h.id !== activeHighlightId));
          setActiveHighlightId(null);
        }}
        onSaveNote={onSaveNote}
      />
    );
  })()
)}
    </div>
  );
};

export default PdfViewer;