import React, { useEffect, useRef, useState } from 'react';
import { Bookmark, ChevronDown, ChevronRight, ChevronUp, FileText, Link2, Plus, Sparkles, Trash2, User, X } from 'lucide-react';

import InsightCard from './InsightCard.jsx';
import MarkdownContent from './MarkdownContent';
import { getMessageMarkdownClassName } from './MessageMarkdownRenderer';
import { normalizeSentenceReferences } from './evidenceCitationModel.js';

const quickTags = ['# 核心结论', '# 证据追问', '# 批判阅读'];
const clampText = (value, maxLength = 72) => {
  const normalized = `${value ?? ''}`.replace(/\s+/g, ' ').trim();
  if (!normalized) {
    return '';
  }

  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized;
};

const EvidenceReferences = ({ references = [], onJumpToSource }) => {
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
                  <div key={source.sourceId} className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="font-semibold">[{source.sourceId}]</span>
                    <span> {source.preview}</span>
                    {source.canJumpToSource && (
                      <button
                        type="button"
                        onClick={() => onJumpToSource?.(source)}
                        className="source-link-chip inline-flex items-center gap-1"
                      >
                        <Link2 size={12} />
                        <span>跳回原文 {source.locationLabel}</span>
                      </button>
                    )}
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

const MessageRoleBadge = ({ role, isSystem }) => {
  if (isSystem) {
    return <span className="chat-role-badge chat-role-system">系统提示</span>;
  }

  if (role === 'user') {
    return <span className="chat-role-badge chat-role-user">你</span>;
  }

  return <span className="chat-role-badge chat-role-ai">Pixiu</span>;
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
  contextTitle = '当前论文',
  contextSummary = '',
  nextActionHint = '',
}) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const condensedContextSummary = clampText(contextSummary, 72);
  const condensedNextAction = clampText(nextActionHint, 28);
  const aiReplyCount = messages.filter((message) => message.role === 'ai' && !message.isSystem).length;

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
        type="button"
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
        type="button"
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
      <div className="theme-panel theme-border border-b px-5 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <div className="theme-text-primary text-sm font-bold">延展问答</div>
              <div className="theme-text-muted text-[11px]">先结论，再依据，按需展开</div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
              <span className="chat-context-chip chat-context-chip-strong">当前论文：{contextTitle}</span>
              {condensedContextSummary && <span className="chat-context-chip">{condensedContextSummary}</span>}
              {condensedNextAction && <span className="chat-context-chip chat-context-chip-accent">下一步：{condensedNextAction}</span>}
            </div>
          </div>
          <div className="chat-header-stat rounded-full bg-pixiu/10 px-2.5 py-1 text-[11px] font-semibold text-pixiu">
            {aiReplyCount} 条 AI 回复
          </div>
        </div>
      </div>

      <div className="chat-message-list flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {messages.map((message, index) => {
          const isUser = message.role === 'user';
          const isSystem = Boolean(message.isSystem);
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
          const citationFooter = references.length > 0 ? (
            <EvidenceReferences references={references} onJumpToSource={onJumpToSource} />
          ) : null;
          const footer = citationFooter || sourceFooter ? (
            <div className="space-y-2">
              {citationFooter}
              {sourceFooter}
            </div>
          ) : null;

          return (
            <div
              key={message.id ?? index}
              className={`group flex items-start gap-2.5 ${isUser ? 'justify-end' : 'justify-start'}`}
            >
              {!isUser && renderMessageActions(message, index)}

              <div className={`chat-message-column max-w-[92%] flex-1 ${isUser ? 'order-first' : ''}`}>
                <div className={`message-frame ${isUser ? 'message-frame-user' : 'message-frame-ai'} ${isSystem ? 'message-frame-system' : ''}`}>
                  <div className="mb-2 flex items-center gap-2">
                    <MessageRoleBadge role={message.role} isSystem={isSystem} />
                    {!isSystem && message.role === 'ai' && (
                      <span className="chat-type-chip">AI 回复</span>
                    )}
                    {isSystem && <span className="chat-type-chip chat-type-chip-system">状态更新</span>}
                    {isUser && <User size={12} className="text-white/75" />}
                  </div>

                  {isUser ? (
                    <div className="text-sm leading-7 text-white">
                      <MarkdownContent className={getMessageMarkdownClassName(message.role, 'chat')}>
                        {message.content}
                      </MarkdownContent>
                    </div>
                  ) : (
                    <InsightCard
                      title={isSystem ? '系统提示' : 'Pixiu 的判断'}
                      icon={!isSystem ? <Sparkles size={14} className="text-pixiu" /> : null}
                      content={message.content}
                      detailsTitle={isSystem ? '展开系统提示' : '展开完整回答'}
                      defaultExpanded={Boolean(isSystem)}
                      className="border-none bg-transparent p-0 shadow-none"
                      footer={footer}
                    />
                  )}
                </div>
              </div>

              {!isUser && renderMessageActions(message, index)}
            </div>
          );
        })}

        {isLoading && (
          <div className="animate-in fade-in slide-in-from-left-2 flex justify-start duration-300">
            <div className="theme-card max-w-[90%] rounded-2xl rounded-bl-none p-4">
              <div className="mb-2 flex items-center gap-2">
                <Sparkles size={14} className="text-pixiu" />
                <span className="text-xs font-semibold text-pixiu">Pixiu 正在整理回答</span>
              </div>
              <div className="theme-card-soft h-2 overflow-hidden rounded-full">
                <div className="h-full w-2/5 animate-pulse rounded-full bg-pixiu" />
              </div>
              <div className="theme-text-secondary mt-2 space-y-1 text-xs leading-5">
                <p>先给一句结论，再补关键依据，最后按需展开完整说明。</p>
                <p>你可以继续读原文，结果会保留在这里。</p>
              </div>
            </div>
            <button
              type="button"
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

      <div className="theme-panel-muted theme-border border-t px-5 py-4">
        <div className="group relative">
          <textarea
            ref={textareaRef}
            rows="2"
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            className="theme-input chat-composer-input w-full resize-none rounded-xl py-3 pl-4 pr-12 outline-none transition-all"
            placeholder={isLoading ? 'Pixiu 正在回答中...' : '先问一个具体问题，例如：这篇论文的核心贡献是否成立？'}
          />
          <button
            type="button"
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

        <div className="mt-2.5 flex flex-wrap gap-2">
          {quickTags.map((tag) => (
            <button
              type="button"
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
