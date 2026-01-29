import React, { useState, useRef, useEffect } from 'react';
import { ChevronRight, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
/**
 * 聊天面板组件
 * @param {Array} messages - 消息列表
 * @param {Function} onSendMessage - 发送消息的回调函数
 */
const ChatPanel = ({ messages = [], onSendMessage }) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 处理发送消息
  const handleSend = () => {
    if (inputValue.trim()) {
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
    '# 交互式助学',
    '# 总结核心贡献',
    '# 评估实验可靠性',
    '# 批判性分析',
  ];

  const handleQuickTag = (tag) => {
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
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div 
              className={`max-w-[90%] p-4 rounded-2xl shadow-sm leading-relaxed ${
                msg.role === 'user' 
                  ? 'bg-blue-600 text-white rounded-br-none' 
                  : 'bg-slate-100 text-slate-800 rounded-bl-none border border-slate-200'
              }`}
            >
              {msg.role === 'ai' && (
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles size={14} className="text-blue-500" />
                  <span className="text-xs font-semibold text-blue-600">AI 助手</span>
                </div>
              )}
              {/* 修复：使用 ReactMarkdown 替换原来的 <p> */}
              <div className={`text-sm ${msg.role === 'user' ? 'text-white' : 'prose prose-sm prose-slate'}`}>
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
              </div>
            </div>
          </div>
        ))}
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
            className="w-full border border-slate-200 rounded-xl pl-4 pr-12 py-3 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none shadow-sm transition-all resize-none"
            placeholder="问问 AI：本文的研究方法有什么局限性？"
          />
          <button 
            onClick={handleSend}
            disabled={!inputValue.trim()}
            className="absolute right-3 bottom-3 p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronRight size={20} />
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {quickTags.map(tag => (
            <button 
              key={tag} 
              onClick={() => handleQuickTag(tag)}
              className="text-[10px] font-bold text-slate-500 bg-white border px-2 py-1 rounded hover:border-blue-400 hover:text-blue-600 transition"
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
