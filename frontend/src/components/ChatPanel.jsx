import React, { useEffect, useRef, useState } from 'react';
import { Bookmark, ChevronDown, ChevronRight, ChevronUp, FileText, Link2, Plus, Sparkles, Trash2, X } from 'lucide-react';

import InsightCard from './InsightCard.jsx';
import MarkdownContent from './MarkdownContent';
import { getMessageMarkdownClassName } from './MessageMarkdownRenderer';
import { normalizeSentenceReferences } from './evidenceCitationModel.js';

const quickTags = ['# 总结核心贡献', '# 评估实验可靠性', '# 批判性分析'];

const EvidenceReferences = ({ references = [] }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!references.length) {
    return null;
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => setIsExpanded((current) => !current)}
        className="source-link-chip inline-flex items-center gap-1"
      >
        <FileText size={12} />
        <span>引用 {references.length} 条</span>
        {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {isExpanded && (
        <div className="space-y-2">
          {references.map((reference) => (
            <div key={reference.id} className="theme-card-soft rounded-xl p-3 text-xs leading-5 theme-text-secondary">
              <div className="theme-text-primary mb-1 font-semibold">{reference.sentence}</div>
              <div className="space-y-1">
                {reference.sources.map((source) => (
                  <div key={source.sourceId}>
                    <span className="font-semibold">[{source.sourceId}]</span>
                    <span> {source.preview}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const ChatPanel = ({
  messages = [],
  onSendMessage,
  onDeleteMessage,
  onSaveToNote,
  onCaptureArtifact,
  onJumpToSource,
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
    if (isLoading) {
      return;
    }

    setInputValue(tag);
    textareaRef.current?.focus();
  };

  const renderMessageActions = (message, index) => (
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
      {message.role === 'ai' && (
        <button
          type="button"
          onClick={() => onCaptureArtifact?.(index)}
          className="rounded-full bg-pixiu/10 p-1.5 text-pixiu opacity-0 transition-opacity hover:bg-pixiu/20 group-hover:opacity-100"
          title="加入工作台"
        >
          <Plus size={14} />
        </button>
      )}
      {message.sourceAnchorId && (
        <button
          type="button"
          onClick={() => onJumpToSource?.(message)}
          className="source-link-chip opacity-0 transition-opacity group-hover:opacity-100"
          title="回到原文位置"
        >
          <Link2 size={12} />
        </button>
      )}
    </div>
  );

  return (
    <div className="theme-panel flex h-full flex-col">
      <div className="theme-panel theme-border border-b px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="theme-text-primary text-sm font-bold">延伸问答</div>
            <div className="theme-text-secondary mt-1 text-xs leading-5">
              这里更适合承接基于当前论文的追问。AI 回复会优先给出摘要，再按需展开完整分析。
            </div>
          </div>
          <div className="rounded-full bg-pixiu/10 px-2.5 py-1 text-[11px] font-semibold text-pixiu">
            {messages.filter((message) => message.role === 'ai').length} 条 AI 回复
          </div>
        </div>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        {messages.map((message, index) => (
          <div
            key={message.id ?? index}
            className={`group flex items-start gap-2 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {message.role === 'user' && renderMessageActions(message, index)}

            {message.role === 'user' ? (
              <div className="max-w-[85%] rounded-2xl rounded-br-none bg-pixiu p-4 text-white shadow-sm">
                <div className="text-sm">
                  <MarkdownContent className={getMessageMarkdownClassName(message.role, 'chat')}>
                    {message.content}
                  </MarkdownContent>
                </div>
              </div>
            ) : (
              <div className="max-w-[90%] flex-1">
                {(() => {
                  const references = normalizeSentenceReferences(message.sentenceSourceMap, message.rag_sources, {
                    target: 'message',
                  });
                  const sourceFooter = message.sourceAnchorId ? (
                    <button
                      type="button"
                      onClick={() => onJumpToSource?.(message)}
                      className="source-link-chip inline-flex items-center gap-1"
                    >
                      <Link2 size={12} />
                      <span>
                        来源 {Number.isFinite(message.sourcePageIndex) ? `p.${message.sourcePageIndex + 1}` : '原文片段'}
                      </span>
                    </button>
                  ) : null;
                  const citationFooter = references.length > 0 ? <EvidenceReferences references={references} /> : null;
                  const footer = citationFooter || sourceFooter ? (
                    <div className="space-y-2">
                      {citationFooter}
                      {sourceFooter}
                    </div>
                  ) : null;

                  return (
                <InsightCard
                  title={message.isSystem ? '系统状态' : 'Pixiu'}
                  icon={!message.isSystem ? <Sparkles size={14} className="text-pixiu" /> : null}
                  content={message.content}
                  detailsTitle="展开完整回答"
                  defaultExpanded={Boolean(message.isSystem)}
                  className="rounded-bl-none"
                  footer={footer}
                />
                  );
                })()}
              </div>
            )}

            {message.role === 'ai' && renderMessageActions(message, index)}
          </div>
        ))}

        {isLoading && (
          <div className="animate-in fade-in slide-in-from-left-2 flex justify-start duration-300">
            <div className="theme-card max-w-[90%] rounded-2xl rounded-bl-none p-4">
              <div className="mb-3 flex items-center gap-2">
                <Sparkles size={14} className="text-pixiu" />
                <span className="text-xs font-semibold text-pixiu">Pixiu 正在生成</span>
              </div>
              <div className="theme-card-soft h-2 overflow-hidden rounded-full">
                <div className="h-full w-2/5 animate-pulse rounded-full bg-pixiu" />
              </div>
              <div className="theme-text-secondary mt-3 text-xs leading-5">
                会先整理一句话摘要，再补充关键要点与完整回答。
              </div>
            </div>
            <button
              onClick={onAbortChat}
              className="theme-danger-button ml-2 self-center rounded-full border border-red-400/10 p-1.5 shadow-sm transition-colors"
              title="停止生成"
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
            placeholder={isLoading ? 'Pixiu 正在回答中...' : '问问 Pixiu：本文的研究方法有什么局限性？'}
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
