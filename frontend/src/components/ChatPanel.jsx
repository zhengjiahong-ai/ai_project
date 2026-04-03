import React, { useState, useRef, useEffect } from 'react';
import { Bookmark, ChevronRight, Sparkles, Trash2, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
/**
 * 聊天面板组件
 * @param {Array} messages - 消息列表
 * @param {Function} onSendMessage - 发送消息的回调函数
 */
const ChatPanel = ({ messages = [], onSendMessage, onDeleteMessage, onSaveToNote, onAbortChat, isLoading = false }) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // 处理发送消息
  const handleSend = () => {
    if (inputValue.trim() && !isLoading) {
      onSendMessage(inputValue.trim());
      setInputValue('');
      // 重置 textarea 高度
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  // 处理键盘事件
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 自动调整 textarea 高度
  const handleInputChange = (e) => {
    setInputValue(e.target.value);
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
  };

  // 快速标签
  const quickTags = [
    '# 总结核心贡献',
    '# 评估实验可靠性',
    '# 批判性分析',
  ];

  const handleQuickTag = (tag) => {
    if (isLoading) return;
    setInputValue(tag);
    textareaRef.current?.focus();
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 对话区域 */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.map((msg, idx) => (
          <div 
            key={idx} 
            className={`flex group items-start gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'user' && (
              <div className="flex flex-col gap-1 shrink-0 mt-2">
                <button 
                  onClick={() => {
                    if (window.confirm("确定删除这条对话记录吗？")) {
                      onDeleteMessage && onDeleteMessage(idx);
                    }
                  }}
                  className="p-1.5 opacity-0 group-hover:opacity-100 transition-opacity rounded-full bg-red-50 text-red-500 hover:bg-red-100"
                  title="删除此消息"
                >
                  <Trash2 size={14} />
                </button>
                <button 
                  onClick={() => onSaveToNote && onSaveToNote(idx)}
                  className="p-1.5 opacity-0 group-hover:opacity-100 transition-opacity rounded-full bg-pixiu/10 text-pixiu hover:bg-pixiu/20"
                  title="收藏至学术笔记"
                >
                  <Bookmark size={14} />
                </button>
              </div>
            )}

            <div 
              className={`max-w-[85%] p-4 rounded-2xl shadow-sm leading-relaxed ${
                msg.role === 'user' 
                  ? 'bg-pixiu text-white rounded-br-none' 
                  : 'bg-slate-100 text-slate-800 rounded-bl-none border border-slate-200'
              }`}
            >
              {msg.role === 'ai' && (
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles size={14} className="text-pixiu" />
                  <span className="text-xs font-semibold text-pixiu">貔貅</span>
                </div>
              )}
              <div className={`text-sm ${msg.role === 'user' ? 'text-white' : 'prose prose-sm prose-slate'}`}>
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
              </div>
            </div>

            {msg.role === 'ai' && (
              <div className="flex flex-col gap-1 shrink-0 mt-2">
                <button 
                  onClick={() => {
                    if (window.confirm("确定删除这条对话记录吗？")) {
                      onDeleteMessage && onDeleteMessage(idx);
                    }
                  }}
                  className="p-1.5 opacity-0 group-hover:opacity-100 transition-opacity rounded-full bg-red-50 text-red-500 hover:bg-red-100"
                  title="删除此消息"
                >
                  <Trash2 size={14} />
                </button>
                <button 
                  onClick={() => onSaveToNote && onSaveToNote(idx)}
                  className="p-1.5 opacity-0 group-hover:opacity-100 transition-opacity rounded-full bg-pixiu/10 text-pixiu hover:bg-pixiu/20"
                  title="收藏至学术笔记"
                >
                  <Bookmark size={14} />
                </button>
              </div>
            )}
          </div>
        ))}

        {/* 正在思考的动画 */}
        {isLoading && (
          <div className="flex justify-start animate-in fade-in slide-in-from-left-2 duration-300">
            <div className="bg-slate-100 text-slate-800 p-4 rounded-2xl rounded-bl-none border border-slate-200 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="flex gap-1">
                  <div className="w-1.5 h-1.5 bg-pixiu rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                  <div className="w-1.5 h-1.5 bg-pixiu rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                  <div className="w-1.5 h-1.5 bg-pixiu rounded-full animate-bounce"></div>
                </div>
                <span className="text-xs font-medium text-slate-500 italic">貔貅 正在思考...</span>
              </div>
            </div>
            {/* 中止按钮 */}
            <button 
              onClick={onAbortChat}
              className="ml-2 p-1.5 bg-white border border-red-100 text-red-500 rounded-full hover:bg-red-50 transition-colors shadow-sm self-center"
              title="中止生成"
            >
              <X size={14} />
            </button>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* 输入区域 */}
      <div className="p-6 border-t bg-slate-50">
        <div className="relative group">
          <textarea 
            ref={textareaRef}
            rows="2"
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            className="w-full border border-slate-200 rounded-xl pl-4 pr-12 py-3 focus:ring-2 focus:ring-pixiu focus:border-transparent outline-none shadow-sm transition-all resize-none disabled:bg-slate-100 disabled:text-slate-400"
            placeholder={isLoading ? "貔貅 正在回答中..." : "问问 貔貅：本文的研究方法有什么局限性？"}
          />
          <button 
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading}
            className="absolute right-3 bottom-3 p-2 bg-pixiu text-white rounded-lg hover:bg-pixiu-dark transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <ChevronRight size={20} />}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {quickTags.map(tag => (
            <button 
              key={tag} 
              onClick={() => handleQuickTag(tag)}
              className="text-[10px] font-bold text-slate-500 bg-white border px-2 py-1 rounded hover:border-pixiu/30 hover:text-pixiu transition"
            >
              {tag}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;
