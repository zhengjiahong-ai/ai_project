import React, { useEffect, useRef, useState } from 'react';
import { Bookmark, ChevronDown, ChevronUp, FileText, Link2, Plus, Send, Trash2, X } from 'lucide-react';

import MarkdownContent from './MarkdownContent';
import { getMessageMarkdownClassName } from './MessageMarkdownRenderer';
import SourceList from './SourceCitation.jsx';
import { normalizeSentenceReferences } from './evidenceCitationModel.ts';

interface ChatJumpSource {
  sourceId?: string;
  sourceAnchorId?: string;
  sourceText?: string;
  sourcePageIndex?: number;
  text?: string;
  pageIndex?: number;
  sectionId?: string;
  preview?: string;
}

interface ChatMessage {
  id?: string | number;
  role: 'user' | 'ai';
  isSystem?: boolean;
  content: string;
  sourceAnchorId?: string;
  sourceText?: string;
  sourcePageIndex?: number;
  sentenceSourceMap?: unknown;
  rag_sources?: unknown;
}

interface EvidenceRef {
  id: string;
  sentence: string;
  sources: ChatJumpSource[];
}

interface ChatPanelProps {
  messages?: ChatMessage[];
  onSendMessage: (text: string) => void;
  onDeleteMessage?: (index: number) => void;
  onSaveToNote?: (index: number) => void;
  onCaptureArtifact?: (index: number) => void;
  onJumpToSource?: (source: ChatJumpSource) => void;
  onAbortChat?: () => void;
  isLoading?: boolean;
  contextLabel?: string;
}

interface EvidenceReferencesProps {
  references?: EvidenceRef[];
  onJumpToSource?: (source: ChatJumpSource) => void;
}

const EvidenceReferences: React.FC<EvidenceReferencesProps> = ({ references = [], onJumpToSource }) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  if (!references.length) return null;

  return (
    <div className="reader-chat-citations">
      <button
        type="button"
        onClick={() => setIsExpanded((current: boolean) => !current)}
        className="reader-chat-citation"
      >
        <FileText size={12} />
        来源 {references.length}
        {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {isExpanded && (
        <div className="mt-3 space-y-2">
          {references.map((reference: EvidenceRef) => (
            <div key={reference.id} className="theme-card-soft rounded-lg p-3 text-xs leading-5 theme-text-secondary">
              <div className="theme-text-primary mb-1 font-semibold">{reference.sentence}</div>
              <div className="mb-2 theme-text-muted">{reference.sources.map((source: ChatJumpSource) => source.preview).join('；')}</div>
              <SourceList sources={reference.sources} onJumpToSource={onJumpToSource} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const ChatPanel: React.FC<ChatPanelProps> = ({
  messages = [],
  onSendMessage,
  onDeleteMessage,
  onSaveToNote,
  onCaptureArtifact,
  onJumpToSource,
  onAbortChat,
  isLoading = false,
  contextLabel = '',
}) => {
  const [inputValue, setInputValue] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSend = (): void => {
    if (!inputValue.trim() || isLoading) return;
    onSendMessage(inputValue.trim());
    setInputValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>): void => {
    setInputValue(event.target.value);
    const textarea = event.target;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
  };

  const renderMessageActions = (message: ChatMessage, index: number): React.ReactNode => (
    <div className="reader-chat-message-actions">
      <button
        type="button"
        onClick={() => {
          if (window.confirm('确定删除这条对话记录吗？')) onDeleteMessage?.(index);
        }}
        className="theme-danger-button rounded-full p-1.5"
        title="删除此消息"
        aria-label="删除此消息"
      >
        <Trash2 size={13} />
      </button>
      <button type="button" onClick={() => onSaveToNote?.(index)} className="reader-chat-action" title="收藏到学术笔记" aria-label="收藏到学术笔记">
        <Bookmark size={13} />
      </button>
      {message.role === 'ai' && (
        <button type="button" onClick={() => onCaptureArtifact?.(index)} className="reader-chat-action" title="加入工作台" aria-label="加入工作台">
          <Plus size={13} />
        </button>
      )}
      {message.sourceAnchorId && (
        <button type="button" onClick={() => onJumpToSource?.(message)} className="reader-chat-action" title="回到原文位置" aria-label="回到原文位置">
          <Link2 size={13} />
        </button>
      )}
    </div>
  );

  return (
    <div className="reader-chat-shell">
      <div className="reader-chat-scroll">
        {contextLabel && <div className="reader-chat-context">▣ {contextLabel}</div>}

        {messages.map((message: ChatMessage, index: number) => {
          const isUser = message.role === 'user';
          const isSystem = Boolean(message.isSystem);
          const references = normalizeSentenceReferences(message.sentenceSourceMap, message.rag_sources, { target: 'message' }) as EvidenceRef[];
          const sourceFooter = message.sourceAnchorId ? (
            <div className="reader-chat-citations">
              <SourceList
                sources={[{
                  sourceId: message.sourceAnchorId,
                  text: message.sourceText || message.content,
                  pageIndex: message.sourcePageIndex,
                  sectionId: message.sourceAnchorId,
                }]}
                onJumpToSource={onJumpToSource}
              />
            </div>
          ) : null;

          if (isUser) {
            return (
              <div key={message.id ?? index} className="reader-chat-user-line group">
                <div className="reader-chat-user-bubble">
                  <MarkdownContent className={getMessageMarkdownClassName(message.role, 'chat')}>{message.content}</MarkdownContent>
                  {renderMessageActions(message, index)}
                </div>
              </div>
            );
          }

          return (
            <article key={message.id ?? index} className={`reader-chat-answer group ${isSystem ? 'reader-chat-answer-system' : ''}`}>
              <div className="reader-chat-answer-head">
                <img src="/貔貅紫白.png" alt="" width="27" height="27" />
                <span>{isSystem ? '系统提示' : '阅读助手'}</span>
                {renderMessageActions(message, index)}
              </div>
              <MarkdownContent className={getMessageMarkdownClassName(message.role, 'chat')}>{message.content}</MarkdownContent>
              <EvidenceReferences references={references} onJumpToSource={onJumpToSource} />
              {sourceFooter}
            </article>
          );
        })}

        {isLoading && (
          <div className="reader-chat-answer reader-chat-loading">
            <div className="reader-chat-answer-head">
              <img src="/貔貅紫白.png" alt="" width="27" height="27" />
              <span>阅读助手</span>
              <button type="button" onClick={onAbortChat} className="theme-danger-button ml-auto rounded-full p-1.5" title="停止生成" aria-label="停止生成">
                <X size={13} />
              </button>
            </div>
            <div className="reader-chat-loading-bar"><span /></div>
            <span className="sr-only">生成中</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="reader-chat-composer">
        <textarea
          ref={textareaRef}
          rows={1}
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          aria-label="输入问题"
          placeholder={isLoading ? '正在回答...' : '输入问题'}
        />
        <button type="button" onClick={handleSend} disabled={!inputValue.trim() || isLoading} className="reader-chat-send" aria-label="发送消息">
          <Send size={18} />
        </button>
      </div>
    </div>
  );
};

export default ChatPanel;
