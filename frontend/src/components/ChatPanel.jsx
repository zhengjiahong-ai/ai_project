import React, { useEffect, useRef, useState } from 'react';
import { Bookmark, ChevronRight, Sparkles, Trash2, X } from 'lucide-react';
import MarkdownContent from './MarkdownContent';
import { getMessageMarkdownClassName } from './MessageMarkdownRenderer';

const quickTags = ['# 总结核心贡献', '# 评估实验可靠性', '# 批判性分析'];

const ChatPanel = ({
  messages = [],
  onSendMessage,
  onDeleteMessage,
  onSaveToNote,
  onAbortChat,
  isLoading = false,
}) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSend = () => {
    if (inputValue.trim() && !isLoading) {
      onSendMessage(inputValue.trim());
      setInputValue('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (event) => {
    setInputValue(event.target.value);
    const textarea = event.target;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
  };

  const handleQuickTag = (tag) => {
    if (isLoading) return;
    setInputValue(tag);
    textareaRef.current?.focus();
  };

  return (
    <div className="theme-panel flex h-full flex-col">
      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        {messages.map((message, index) => (
          <div
            key={index}
            className={`group flex items-start gap-2 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {message.role === 'user' && (
              <div className="mt-2 flex shrink-0 flex-col gap-1">
                <button
                  onClick={() => {
                    if (window.confirm('确定删除这条对话记录吗？')) {
                      onDeleteMessage?.(index);
                    }
                  }}
                  className="theme-danger-button rounded-full p-1.5 opacity-0 transition-opacity group-hover:opacity-100"
                  title="删除此消息"
                >
                  <Trash2 size={14} />
                </button>
                <button
                  onClick={() => onSaveToNote?.(index)}
                  className="rounded-full bg-pixiu/10 p-1.5 text-pixiu opacity-0 transition-opacity hover:bg-pixiu/20 group-hover:opacity-100"
                  title="收藏到学术笔记"
                >
                  <Bookmark size={14} />
                </button>
              </div>
            )}

            <div
              className={`max-w-[85%] rounded-2xl p-4 shadow-sm ${
                message.role === 'user'
                  ? 'rounded-br-none bg-pixiu text-white'
                  : 'theme-card rounded-bl-none leading-relaxed'
              }`}
            >
              {message.role === 'ai' && (
                <div className="mb-2 flex items-center gap-2">
                  <Sparkles size={14} className="text-pixiu" />
                  <span className="text-xs font-semibold text-pixiu">貔貅</span>
                </div>
              )}
              <div className="text-sm">
                <MarkdownContent className={getMessageMarkdownClassName(message.role, 'chat')}>
                  {message.content}
                </MarkdownContent>
              </div>
            </div>

            {message.role === 'ai' && (
              <div className="mt-2 flex shrink-0 flex-col gap-1">
                <button
                  onClick={() => {
                    if (window.confirm('确定删除这条对话记录吗？')) {
                      onDeleteMessage?.(index);
                    }
                  }}
                  className="theme-danger-button rounded-full p-1.5 opacity-0 transition-opacity group-hover:opacity-100"
                  title="删除此消息"
                >
                  <Trash2 size={14} />
                </button>
                <button
                  onClick={() => onSaveToNote?.(index)}
                  className="rounded-full bg-pixiu/10 p-1.5 text-pixiu opacity-0 transition-opacity hover:bg-pixiu/20 group-hover:opacity-100"
                  title="收藏到学术笔记"
                >
                  <Bookmark size={14} />
                </button>
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="animate-in fade-in slide-in-from-left-2 flex justify-start duration-300">
            <div className="theme-card flex items-center gap-3 rounded-2xl rounded-bl-none p-4">
              <div className="flex gap-1">
                <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-pixiu [animation-delay:-0.3s]" />
                <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-pixiu [animation-delay:-0.15s]" />
                <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-pixiu" />
              </div>
              <span className="theme-text-secondary text-xs font-medium italic">貔貅 正在思考...</span>
            </div>
            <button
              onClick={onAbortChat}
              className="theme-danger-button ml-2 self-center rounded-full border border-red-400/10 p-1.5 shadow-sm transition-colors"
              title="中止生成"
            >
              <X size={14} />
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="theme-panel-muted theme-border border-t p-6">
        <div className="group relative">
          <textarea
            ref={textareaRef}
            rows="2"
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            className="theme-input w-full resize-none rounded-xl py-3 pl-4 pr-12 outline-none transition-all"
            placeholder={isLoading ? '貔貅 正在回答中...' : '问问 貔貅：本文的研究方法有什么局限性？'}
          />
          <button
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading}
            className="absolute bottom-3 right-3 rounded-lg bg-pixiu p-2 text-white shadow-md transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? (
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            ) : (
              <ChevronRight size={20} />
            )}
          </button>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {quickTags.map((tag) => (
            <button
              key={tag}
              onClick={() => handleQuickTag(tag)}
              className="theme-quick-tag rounded px-2 py-1 text-[10px] font-bold transition"
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
