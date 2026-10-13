import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Check, ChevronDown, ChevronUp, Copy, FileText, Link2, Maximize2, MessageSquare, Minimize2, PanelRightClose, Plus, Search, Send, Trash2, X } from 'lucide-react';

import './ChatPanelInteraction.css';

import MarkdownContent from './MarkdownContent';
import CritiqueContent, { hasGroupedCritique } from './CritiqueContent';
import { getMessageMarkdownClassName } from './MessageMarkdownRenderer';
import SourceList from './SourceCitation.jsx';
import CollapsedSources from './CollapsedSources';
import WorkbenchPopover from './WorkbenchPopover';
import { normalizeSentenceReferences } from './evidenceCitationModel.ts';
import { getSkillSuggestions, parseSkillCommand, resolveConversationSkill } from '../utils/conversationSkills';
import { artifactChatPreview } from '../utils/artifactChatPreview';
import useConversationDraft from '../hooks/useConversationDraft';
import { completeMaterialMention, materialDraft, pendingMaterialMention, withMaterialReferences, type MentionMaterial } from '../utils/materialMentions';

interface ChatJumpSource {
  sourceId?: string;
  sourceAnchorId?: string;
  sourceText?: string;
  sourcePageIndex?: number;
  sourcePdfId?: string;
  text?: string;
  pageIndex?: number;
  sectionId?: string;
  preview?: string;
}

interface ChatMessage {
  critique?: unknown;
  artifactId?: string;
  artifactIsCurrent?: boolean;
  synthetic?: boolean;
  id?: string | number;
  role: 'user' | 'ai';
  isSystem?: boolean;
  content: string;
  sourceAnchorId?: string;
  sourceText?: string;
  sourcePageIndex?: number;
  sourcePdfId?: string;
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
  onSendMessage: (text: string) => void | boolean | Promise<void | boolean>;
  onDraftChange?: (text: string) => void;
  onDeleteMessage?: (index: number) => void;
  onSaveToNote?: (index: number) => void | Promise<unknown>;
  onCaptureArtifact?: (index: number) => void | Promise<unknown>;
  onOpenArtifact?: (id: string) => void;
  onFollowupIssue?: (message: ChatMessage, issueId: string) => void;
  onJumpToSource?: (source: ChatJumpSource) => void;
  onAbortChat?: () => void;
  isLoading?: boolean;
  showLoadingIndicator?: boolean;
  contextLabel?: string;
  enableSkills?: boolean;
  materials?: MentionMaterial[];
  focusedMaterialId?: string | null;
  conversationId?: string;
  renderMessageAfter?: (message: ChatMessage, index: number) => React.ReactNode;
  historyContent?: React.ReactNode;
  composerContext?: React.ReactNode;
  currentActivity?: React.ReactNode;
  showHeader?: boolean;
  onCollapse?: () => void;
  focusMessage?: { id?: string | number; index?: number; token: number };
  starterPrompts?: Array<{ label: string; text: string; onSelect?: () => void }>;
  sendLabel?: string;
  inputPlaceholder?: string;
  /** Research capabilities for source scope and budget controls in the material popover. */
  researchCapabilities?: {
    engineVersion?: string;
    enabled?: boolean;
    externalAcademic?: boolean;
    fulltext?: boolean;
    budgetProfiles?: string[];
  } | null;
  /** Current research source policy mode from parent state. */
  researchSourcePolicy?: 'task_only' | 'academic_external';
  researchContextOptions?: Array<{ id: string; title: string }>;
  researchContextRefs?: string[];
  onResearchContextRefsChange?: (refs: string[]) => void;
  /** Callback when user changes research source policy. */
  onResearchSourcePolicyChange?: (mode: 'task_only' | 'academic_external') => void;
  /** Current research budget profile from parent state. */
  researchBudgetProfile?: string;
  /** Callback when user changes research budget profile. */
  onResearchBudgetProfileChange?: (profile: string) => void;
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
        引用依据 {references.length} 处
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
  onDraftChange,
  onDeleteMessage,
  onSaveToNote,
  onCaptureArtifact,
  onOpenArtifact,
  onFollowupIssue,
  onJumpToSource,
  onAbortChat,
  isLoading = false,
  showLoadingIndicator = true,
  contextLabel = '',
  enableSkills = false,
  materials = [],
  focusedMaterialId,
  conversationId,
  starterPrompts = [],
  sendLabel = '发送消息', inputPlaceholder,
  renderMessageAfter, historyContent, composerContext, currentActivity, focusMessage, showHeader = false, onCollapse,
  researchCapabilities, researchSourcePolicy = 'task_only', onResearchSourcePolicyChange,
  researchContextOptions = [], researchContextRefs = [], onResearchContextRefsChange,
  researchBudgetProfile = 'standard', onResearchBudgetProfileChange,
}) => {
  const [inputValue, setInputValue, draftError, clearInput] = useConversationDraft(conversationId);
  const draftMaterials: { text: string; references: string[] } = enableSkills ? materialDraft(inputValue) : { text: inputValue, references: [] };
  const visibleInput = draftMaterials.text;
  useEffect(() => { onDraftChange?.(inputValue); }, [inputValue, onDraftChange]);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [sendError, setSendError] = useState('');
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const atBottomRef = useRef(true);
  const previousMessages = useRef(messages);
  const previousTask = useRef(conversationId);
  const messageElements = useRef(new Map<number, HTMLElement>());
  const [hasNewResults, setHasNewResults] = useState(false);
  const [search, setSearch] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [highlightedMessage, setHighlightedMessage] = useState<string | null>(null);
  const searchInput = useRef<HTMLInputElement | null>(null), searchTrigger = useRef<HTMLButtonElement | null>(null);
  useEffect(() => { if (searchOpen) searchInput.current?.focus(); }, [searchOpen]);
  const [copiedMessage, setCopiedMessage] = useState<string | null>(null);
  const [copyError, setCopyError] = useState('');
  const [saveStates, setSaveStates] = useState<Record<string, 'saving' | 'saved' | 'error'>>({});
  const [savedTargets, setSavedTargets] = useState<Record<string, string>>({});
  const savePending = useRef(new Set<string>());
  const latestDraft = useRef(inputValue);
  latestDraft.current = inputValue;
  const saveKey = (message: ChatMessage, index: number) => JSON.stringify([conversationId, message.id ?? index, message.content]);
  const messageId = (message: ChatMessage, index: number) => String(message.id ?? `index-${index}`);
  const scrollKey = `pixiu-conversation-scroll:${JSON.stringify(conversationId || 'legacy')}`;
  const jumpToMessage = (index: number) => {
    atBottomRef.current = false;
    messageElements.current.get(index)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const message = messages[index];
    if (message) setHighlightedMessage(messageId(message, index));
  };
  useEffect(() => {
    if (highlightedMessage === null) return;
    const timeout = window.setTimeout(() => setHighlightedMessage(null), 5000);
    return () => window.clearTimeout(timeout);
  }, [highlightedMessage]);
  const scrollToLatest = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    atBottomRef.current = true;
    setHasNewResults(false);
  };
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [inputExpanded, setInputExpanded] = useState(false);
  const composerRef = useRef<HTMLDivElement | HTMLDialogElement | null>(null);
  const expandButtonRef = useRef<HTMLButtonElement | null>(null);
  const previouslyExpanded = useRef(false);
  const ComposerSurface = inputExpanded ? 'dialog' : 'div';
  useLayoutEffect(() => {
    if (!inputExpanded) {
      if (previouslyExpanded.current) expandButtonRef.current?.focus();
      previouslyExpanded.current = false;
      return;
    }
    previouslyExpanded.current = true;
    const dialog = composerRef.current as HTMLDialogElement;
    dialog.showModal?.();
    textareaRef.current?.focus();
    return () => { if (dialog.open) dialog.close(); };
  }, [inputExpanded]);
  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const maxHeight = parseFloat(getComputedStyle(textarea).maxHeight) || 160;
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
  }, [inputValue, conversationId, inputExpanded]);
  const [suggestionsDismissed, setSuggestionsDismissed] = useState(false);
  const suggestionsRef = useRef<HTMLDivElement | null>(null);
  const skillSuggestions = enableSkills && !suggestionsDismissed ? getSkillSuggestions(visibleInput) : [];
  const pendingMention = enableSkills && !suggestionsDismissed ? pendingMaterialMention(visibleInput) : null;
  const suggestionsOpen = Boolean(pendingMention || skillSuggestions.length);
  useEffect(() => {
    if (!suggestionsOpen) return;
    const outside = (event: PointerEvent) => {
      if (!suggestionsRef.current?.contains(event.target as Node) && !textareaRef.current?.contains(event.target as Node)) setSuggestionsDismissed(true);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented) {
        event.preventDefault(); event.stopPropagation(); setSuggestionsDismissed(true); textareaRef.current?.focus();
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [suggestionsOpen]);
  const materialSuggestions = pendingMention ? materials.filter(material =>
    [material.title, material.filename, material.id].some(label => label?.toLocaleLowerCase().includes(pendingMention.query))) : [];

  const explicitSkill = enableSkills ? parseSkillCommand(inputValue) : null;
  const recognizedSkill = enableSkills ? resolveConversationSkill(inputValue) : null;
  const selectedMentions = draftMaterials.references;
  const materialLabel = (reference: string) => {
    const material = materials.find(item => [item.id, item.title, item.filename].includes(reference));
    return material?.title || material?.filename || reference;
  };
  const searchResults = search.trim() ? messages.map((message, index) => ({ message, index }))
    .filter(({ message }) => message.content.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())) : [];

  useLayoutEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return;
    let stored: string | null = null;
    try { stored = sessionStorage.getItem(scrollKey); } catch { /* storage may be unavailable */ }
    scroller.scrollTop = stored === null ? scroller.scrollHeight : Number(stored) || 0;
    atBottomRef.current = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 48;
    setHasNewResults(false);
    setSearch('');
    setSearchOpen(false);
    setHighlightedMessage(null);
    setSuggestionsDismissed(false);
    return () => {
      try { sessionStorage.setItem(scrollKey, String(scroller.scrollTop)); } catch { /* preserve in-page navigation */ }
    };
  }, [scrollKey]);

  useEffect(() => {
    if (previousTask.current !== conversationId) {
      previousTask.current = conversationId;
      previousMessages.current = messages;
      return;
    }
    const changed = messages.length !== previousMessages.current.length || messages.some((message, index) =>
      message.content !== previousMessages.current[index]?.content || message.artifactId !== previousMessages.current[index]?.artifactId);
    previousMessages.current = messages;
    if (!changed) return;
    if (atBottomRef.current) scrollToLatest();
    else setHasNewResults(true);
  }, [messages, conversationId]);

  // Slots can receive completed results without changing the message array.
  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller || typeof MutationObserver === 'undefined') return;
    let previousText = scroller.textContent;
    const observer = new MutationObserver(() => {
      const text = scroller.textContent;
      if (text === previousText) return;
      previousText = text;
      if (atBottomRef.current) scrollToLatest();
      else setHasNewResults(true);
    });
    observer.observe(scroller, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [scrollKey]);

  const appliedFocus = useRef('');
  useEffect(() => {
    if (!focusMessage) return;
    const requestKey = JSON.stringify([conversationId, focusMessage.token]);
    if (appliedFocus.current === requestKey) return;
    const index = focusMessage.id !== undefined ? messages.findIndex(message => String(message.id) === String(focusMessage.id)) : focusMessage.index;
    if (index !== undefined && index >= 0) { appliedFocus.current = requestKey; jumpToMessage(index); }
  }, [focusMessage, messages, conversationId]);

  const saveMessage = async (message: ChatMessage, index: number) => {
    const key = saveKey(message, index);
    if (savePending.current.has(key) || saveStates[key] === 'saved') return;
    const save = message.role === 'ai' ? onCaptureArtifact : onSaveToNote || onCaptureArtifact;
    if (!save) return;
    savePending.current.add(key);
    setSaveStates(current => ({ ...current, [key]: 'saving' }));
    try {
      const saved = await save(index);
      if (saved === false) throw new Error('保存未完成');
      if (typeof saved === 'string') setSavedTargets(current => ({ ...current, [key]: saved }));
      setSaveStates(current => ({ ...current, [key]: 'saved' }));
    } catch {
      setSaveStates(current => ({ ...current, [key]: 'error' }));
    } finally { savePending.current.delete(key); }
  };

  const handleSend = async (): Promise<void> => {
    if (!visibleInput.trim() || isLoading || submittingRef.current) return;
    const submittedText = inputValue;
    submittingRef.current = true;
    setSubmitting(true); setSendError('');
    try {
      const action = onSendMessage(submittedText.trim());
      const accepted = typeof (action as Promise<void | boolean>)?.then === 'function' ? await action : action;
      if (accepted === false) return;
      setInputExpanded(false);
      if (latestDraft.current === submittedText) clearInput(submittedText);
      if (latestDraft.current === submittedText && textareaRef.current) textareaRef.current.style.height = 'auto';
    } catch (error) {
      setSendError((error as Error).message || '发送失败，输入已保留。');
    } finally { submittingRef.current = false; setSubmitting(false); }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.nativeEvent.isComposing || event.keyCode === 229) return;
    if (event.key === 'Enter' && !event.shiftKey && (!inputExpanded || event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>): void => {
    setSuggestionsDismissed(false);
    setInputValue(enableSkills ? withMaterialReferences(event.target.value, selectedMentions) : event.target.value);
  };

  const renderMessageActions = (message: ChatMessage, index: number): React.ReactNode => message.synthetic ? null : (
    <div className="reader-chat-message-actions">
      <button type="button" className="reader-chat-action" aria-label={message.role === 'ai' ? '复制回答' : '复制消息'} title="复制内容" onClick={async () => {
        try { await navigator.clipboard.writeText(message.content); setCopiedMessage(messageId(message, index)); setCopyError(''); }
        catch { setCopyError('未能复制，请选择正文复制。'); }
      }}><Copy size={13} />{copiedMessage === messageId(message, index) && '已复制'}</button>
      {onDeleteMessage && <WorkbenchPopover label="消息更多操作">
      {(close: (restore?: boolean) => void) => <button
        type="button"
        onClick={() => {
          close();
          if (window.confirm('确定删除这条对话记录吗？')) onDeleteMessage(index);
        }}
        className="theme-danger-button rounded-full p-1.5"
        title="删除此消息"
        aria-label="删除此消息"
      >
        <Trash2 size={13} />
        删除消息
      </button>}
      </WorkbenchPopover>}
      {(message.artifactId || savedTargets[saveKey(message, index)]) ? (
        <button type="button" onClick={() => onOpenArtifact?.(message.artifactId || savedTargets[saveKey(message, index)])} disabled={!onOpenArtifact} className="reader-chat-action" title={message.role === 'user' ? '查看笔记' : '打开完整成果'} aria-label={message.role === 'user' ? '查看笔记' : '打开完整成果'}>
          <FileText size={13} />{saveStates[saveKey(message, index)] === 'saved' && <span role="status">已保存 · </span>}{message.role === 'user' ? '查看笔记' : '查看成果'}
        </button>
      ) : (message.role === 'ai' ? onCaptureArtifact : onSaveToNote || onCaptureArtifact) && (
        <button type="button" onClick={() => saveMessage(message, index)} className="reader-chat-action"
          disabled={['saving', 'saved'].includes(saveStates[saveKey(message, index)])}
          title="保存" aria-label={saveStates[saveKey(message, index)] === 'saving' ? '保存中' : saveStates[saveKey(message, index)] === 'saved' ? '已保存' : '保存'}>
          <Plus size={13} /> {saveStates[saveKey(message, index)] === 'saving' ? '保存中' : saveStates[saveKey(message, index)] === 'saved' ? '已保存' : '保存'}
        </button>
      )}
      {saveStates[saveKey(message, index)] === 'error' && <span role="alert">保存失败，请重试</span>}
      {message.sourceAnchorId && (
        <button type="button" onClick={() => onJumpToSource?.(message)} className="reader-chat-action" title="回到原文位置" aria-label="回到原文位置">
          <Link2 size={13} />
        </button>
      )}
    </div>
  );

  return (
    <div className="reader-chat-shell">
      <div className={showHeader ? 'unified-pane-head chat-panel-heading' : 'chat-history-tools'}>
        {showHeader && <><MessageSquare size={17} /><strong>对话</strong></>}
        <button ref={searchTrigger} type="button" aria-label="查找对话" title="查找对话" aria-expanded={searchOpen} onClick={() => { setSearchOpen(value => !value); setSearch(''); }}><Search size={16} /></button>
        {onCollapse && <button type="button" className="unified-pane-hide" title="向右收起对话区" onClick={onCollapse} aria-label="收起对话区"><PanelRightClose size={16} /></button>}
      </div>
      {searchOpen && <div className="chat-history-search">
        <input ref={searchInput} aria-label="搜索对话" placeholder="搜索对话" value={search} onChange={event => setSearch(event.target.value)} onKeyDown={event => {
          if (event.key === 'Escape') { event.preventDefault(); setSearch(''); setSearchOpen(false); searchTrigger.current?.focus(); }
        }} />
        {search && <button type="button" onClick={() => setSearch('')} aria-label="清除对话搜索"><X size={13} /></button>}
        {search.trim() && <div className="chat-search-results" role="group" aria-label="对话搜索结果">
          <span>{searchResults.length} 条匹配</span>
          {searchResults.map(({ message, index }) => <button key={messageId(message, index)} type="button" onClick={() => jumpToMessage(index)}>
            第 {index + 1} 条 · {message.content.slice(0, 70)}
          </button>)}
        </div>}
      </div>}
      <div className="reader-chat-scroll" ref={scrollRef} onScroll={event => {
        const node = event.currentTarget;
        atBottomRef.current = node.scrollHeight - node.scrollTop - node.clientHeight < 48;
        if (atBottomRef.current) setHasNewResults(false);
        try { sessionStorage.setItem(scrollKey, String(node.scrollTop)); } catch { /* optional persistence */ }
      }}>

        {!messages.length && !isLoading && starterPrompts.length > 0 && <div className="reader-chat-start" aria-label="对话起点">
          <strong>从一个问题开始</strong>
          <p>{materials.length ? '告诉我哪里读不懂，或选择一个起点。' : '先上传论文，或告诉我你想了解的概念。'}</p>
          <div>{starterPrompts.map(prompt => <button key={prompt.label} type="button" disabled={submitting || Boolean(visibleInput.trim())}
            onClick={() => { if (prompt.onSelect) prompt.onSelect(); else { setInputValue(withMaterialReferences(prompt.text, selectedMentions)); textareaRef.current?.focus(); } }}>{prompt.label}</button>)}</div>
        </div>}

        {messages.map((message: ChatMessage, index: number) => {
          const isUser = message.role === 'user';
          const isSystem = Boolean(message.isSystem);
          const grouped = hasGroupedCritique(message);
          const displayedContent = message.artifactId && !isUser && !grouped ? artifactChatPreview(message.content) : message.content;
          const references = normalizeSentenceReferences(message.sentenceSourceMap, message.rag_sources, { target: 'message' }) as EvidenceRef[];
          const sourceFooter = message.sourceAnchorId ? (
            <div className="reader-chat-citations">
              <SourceList
                sources={[{
                  sourceId: message.sourceAnchorId,
                  text: message.sourceText || message.content,
                  pageIndex: message.sourcePageIndex,
                  sectionId: message.sourceAnchorId,
                  pdfId: message.sourcePdfId,
                }]}
                onJumpToSource={onJumpToSource}
              />
            </div>
          ) : null;

          if (isUser) {
            return (
              <div key={message.id ?? index} id={`chat-message-${encodeURIComponent(messageId(message, index))}`} data-message-id={messageId(message, index)} data-message-index={index}
                ref={node => { if (node) messageElements.current.set(index, node); else messageElements.current.delete(index); }} className={`chat-message-anchor ${highlightedMessage === messageId(message, index) ? 'chat-message-highlight' : ''}`}>
              <div className="reader-chat-user-line group">
                <div className="reader-chat-user-bubble">
                  <MarkdownContent className={getMessageMarkdownClassName(message.role, 'chat')}>{message.content}</MarkdownContent>
                </div>
                {renderMessageActions(message, index)}
              </div>
              {renderMessageAfter?.(message, index)}
              </div>
            );
          }

          return (
            <article key={message.id ?? index} id={`chat-message-${encodeURIComponent(messageId(message, index))}`} data-message-id={messageId(message, index)} data-message-index={index}
              ref={node => { if (node) messageElements.current.set(index, node); else messageElements.current.delete(index); }} className={`reader-chat-answer group ${isSystem ? 'reader-chat-answer-system' : ''} ${highlightedMessage === messageId(message, index) ? 'chat-message-highlight' : ''}`}>
              {isSystem && <div className="reader-chat-answer-head">系统提示</div>}
              {message.artifactIsCurrent === false && <p className="chat-history-version">此回答对应旧版本。<button type="button" onClick={() => onOpenArtifact?.(message.artifactId!)}>查看当前成果</button></p>}
              <CritiqueContent value={message} text={displayedContent} papers={materials} className={getMessageMarkdownClassName(message.role, 'chat')}
                onJumpToSource={onJumpToSource} onFollowup={message.artifactId && message.artifactIsCurrent !== false && onFollowupIssue ? (issueId: string) => onFollowupIssue(message, issueId) : undefined} />
              {!grouped && <EvidenceReferences references={references} onJumpToSource={onJumpToSource} />}
              {sourceFooter}
              {!grouped && !references.length && !message.sourceAnchorId && <CollapsedSources value={message} onJumpToSource={onJumpToSource} />}
              {renderMessageAfter?.(message, index)}
              {renderMessageActions(message, index)}
            </article>
          );
        })}

        {isLoading && showLoadingIndicator && (
          <div className="reader-chat-answer reader-chat-loading">
            <div className="reader-chat-answer-head">
              <img src="/貔貅紫白.png" alt="" width="27" height="27" />
              <span>阅读助手</span>

            </div>
            <div className="reader-chat-loading-bar"><span /></div>
            <span className="sr-only" role="status">生成中</span>
          </div>
        )}

        {historyContent}
        <div ref={messagesEndRef} />
      </div>

      {hasNewResults && <button type="button" className="chat-new-results" onClick={scrollToLatest}>有新结果 · 查看最新</button>}
      {currentActivity && <div className="chat-current-activity">{currentActivity}</div>}
      <ComposerSurface ref={(node: HTMLDivElement | HTMLDialogElement | null) => { composerRef.current = node; }} aria-label={inputExpanded ? '全屏输入' : undefined}
        onCancel={event => { event.preventDefault(); setInputExpanded(false); }}
        className={`workbench-composer-container ${enableSkills ? 'with-tools' : ''} ${isLoading ? 'is-generating' : ''} ${inputExpanded ? 'is-expanded' : ''}`}>
      {inputExpanded && <div className="chat-expanded-heading"><strong>编辑问题</strong><span>Enter 换行 · Ctrl / ⌘ + Enter 发送</span></div>}
      <button ref={expandButtonRef} type="button" className="chat-expand-input" aria-label={inputExpanded ? '收起输入' : '展开输入'}
        title={inputExpanded ? '收起输入（Esc）' : '展开输入'} aria-expanded={inputExpanded} aria-haspopup={inputExpanded ? undefined : 'dialog'}
        onClick={() => setInputExpanded(value => !value)}>{inputExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}</button>
      <div className="reader-chat-composer">
        <textarea ref={textareaRef} rows={2} value={visibleInput} onChange={handleInputChange} onKeyDown={handleKeyDown}
          aria-label="输入问题" placeholder={inputPlaceholder || (enableSkills ? '输入问题，/ 选功能，@ 选材料' : '输入问题')} />
      </div>
      {(composerContext !== undefined ? composerContext : contextLabel) && <div className="reader-chat-context chat-composer-context">{composerContext !== undefined ? composerContext : contextLabel}</div>}
      {copyError && <p className="reader-chat-draft-error" role="alert">{copyError}</p>}
      {(draftError || sendError) && <p className="reader-chat-draft-error" role="alert">{draftError || sendError}</p>}
      {enableSkills && <div className="chat-composer-tools">
        <WorkbenchPopover label="对话材料" className="chat-material-selector" align="left" trigger={<><FileText size={14} /><span>{selectedMentions.length ? `指定材料 · ${selectedMentions.length}篇` : `全部材料 · ${materials.length}篇`}</span><ChevronDown size={12} /></>}>
          {(close: (restore?: boolean) => void) => <>
            <div className="chat-picker-heading"><strong>本轮对话材料</strong><span>选择即生效</span></div>
            <button type="button" className="chat-material-all" aria-label="使用本任务全部材料" aria-pressed={!selectedMentions.length}
              onClick={() => setInputValue(visibleInput)}>
              <span className="chat-picker-check" aria-hidden="true">{!selectedMentions.length && <Check size={14} />}</span>
              <span>任务全部材料</span><span className="chat-picker-count">{materials.length} 篇</span>
            </button>
            <div className="chat-picker-section">或指定论文 · 可多选</div>
            <div className="chat-material-options">
              {materials.map(material => {
                const title = material.title || material.filename || material.id;
                const token = completeMaterialMention('@', material, materials).trim();
                const reference = materialDraft(token).references[0];
                const selected = selectedMentions.includes(reference) || selectedMentions.includes(material.id);
                return <label key={material.id} className={`chat-material-option ${selected ? 'is-selected' : ''}`}>
                  <input type="checkbox" aria-label={title} checked={selected} onChange={() => {
                    setInputValue(withMaterialReferences(visibleInput, selected
                      ? selectedMentions.filter(item => item !== reference && item !== material.id)
                      : [...selectedMentions, reference]));
                  }} />
                  <FileText size={15} aria-hidden="true" />
                  <span className="chat-material-name" title={title}>{title}</span>
                  {material.id === focusedMaterialId && <span className="chat-material-reading">阅读中</span>}
                </label>;
              })}
              {!materials.length && <p className="workbench-menu-caption">任务中还没有论文</p>}
            </div>
            <div className="chat-picker-footer"><span>{selectedMentions.length ? `已指定 ${selectedMentions.length} 篇` : '使用任务全部材料'}</span>
              <button type="button" onClick={() => { close(false); textareaRef.current?.focus(); }}>完成</button></div>
            {recognizedSkill?.skillId === 'research' && <>
              {researchCapabilities?.enabled && researchContextOptions.length > 0 && <details className="chat-research-budget">
                <summary>参考笔记与成果{researchContextRefs.length ? ` · ${researchContextRefs.length}` : ''}</summary>
                <p className="workbench-menu-caption">帮助理解研究目标；论文事实仍回查原文。最多选四份。</p>
                {researchContextOptions.map(value => <label key={value.id} className="chat-material-option">
                  <input type="checkbox" checked={researchContextRefs.includes(value.id)}
                    disabled={!researchContextRefs.includes(value.id) && researchContextRefs.length >= 4}
                    onChange={() => onResearchContextRefsChange?.(researchContextRefs.includes(value.id)
                      ? researchContextRefs.filter(ref => ref !== value.id) : [...researchContextRefs, value.id])} />
                  <span className="chat-material-name">{value.title}</span>
                </label>)}
              </details>}
              <fieldset className="chat-research-scope">
                <legend>资料来源</legend>
                <div className="chat-research-scope-options">
                  <label className="chat-research-scope-option">
                    <input type="radio" name="research-source-policy" checked={researchSourcePolicy === 'task_only'}
                      onChange={() => onResearchSourcePolicyChange?.('task_only')} />
                    <span>仅任务材料</span>
                  </label>
                  <label className="chat-research-scope-option">
                    <input type="radio" name="research-source-policy" checked={researchSourcePolicy === 'academic_external'}
                      disabled={!researchCapabilities?.externalAcademic}
                      onChange={() => onResearchSourcePolicyChange?.('academic_external')} />
                    <span>补充外部文献</span>
                    {!researchCapabilities?.externalAcademic && <small>暂未开放</small>}
                  </label>
                </div>
                {researchSourcePolicy === 'academic_external' && !researchCapabilities?.externalAcademic &&
                  <p className="chat-research-unavailable">外部学术检索能力尚未配置，当前仅可使用任务材料。</p>}
              </fieldset>
              {researchCapabilities?.enabled && (researchCapabilities?.budgetProfiles?.length ?? 0) > 1 && <details className="chat-research-budget"><summary>研究设置</summary><fieldset>
                <legend>预算档位</legend>
                <div className="chat-research-budget-options">
                  {(researchCapabilities?.budgetProfiles || ['standard', 'extended']).map(profile =>
                    <label key={profile} className="chat-research-budget-option">
                      <input type="radio" name="research-budget" checked={researchBudgetProfile === profile}
                        onChange={() => onResearchBudgetProfileChange?.(profile)} />
                      <span>{profile === 'standard' ? '标准' : profile === 'extended' ? '扩展' : profile}</span>
                    </label>)}
                </div>
              </fieldset></details>}
            </>}
          </>}
        </WorkbenchPopover>
        <WorkbenchPopover label="功能" className="chat-function-selector" align="left" trigger={<><span>功能</span><ChevronDown size={12} /></>}>
          {(close: (restore?: boolean) => void) => <><div className="chat-picker-heading"><strong>选择功能</strong><span>选后继续描述需求</span></div>
            {getSkillSuggestions('/').map(skill => <button key={skill.id} type="button" className="chat-function-option" aria-label={`/${skill.command}`}
              aria-pressed={explicitSkill?.skillId === skill.id} onClick={() => {
                setInputValue(`/${skill.command} ${inputValue.replace(/^\s*\/[^\s]*\s*/u, '')}`);
                close(false); textareaRef.current?.focus();
              }}><span><strong>{skill.command}</strong><small>{skill.description}</small></span><code>/{skill.command}</code></button>)}
          </>}
        </WorkbenchPopover>
        {recognizedSkill && <span className="chat-draft-chip">{recognizedSkill.command}
          {explicitSkill && <button type="button" aria-label={`取消${explicitSkill.command}功能`} onClick={() => setInputValue(inputValue.replace(/^\s*\/[^\s]+\s*/u, ''))}><X size={12} /></button>}
        </span>}
        {selectedMentions.map(label => <span key={label} className="chat-draft-chip" title={materialLabel(label)}><span className="chat-draft-chip-label">{materialLabel(label).split(/[:：]/u)[0]}</span>
          <button type="button" aria-label={`移除材料 ${materialLabel(label)}`} onClick={() => setInputValue(withMaterialReferences(visibleInput, selectedMentions.filter(reference => reference !== label)))}><X size={12} /></button>
        </span>)}
      </div>}
      {messages.length > 0 && !isLoading && !visibleInput.trim() && starterPrompts.length > 0 && <details className="chat-next-steps"><summary>下一步</summary><div>{starterPrompts.map(prompt => <button key={prompt.label} type="button" onClick={() => { if (prompt.onSelect) prompt.onSelect(); else { setInputValue(withMaterialReferences(prompt.text, selectedMentions)); textareaRef.current?.focus(); } }}>{prompt.label}</button>)}</div></details>}
      {pendingMention && (
        <div ref={suggestionsRef} className="chat-composer-menu theme-panel theme-border mx-4 max-h-48 overflow-auto rounded-lg border p-1" role="group" aria-label="选择任务材料">
          {materialSuggestions.map(material => <button key={material.id} type="button"
            className="theme-text-primary block w-full rounded px-3 py-2 text-left text-sm hover:bg-[var(--panel-muted)]"
            onClick={() => { setInputValue(withMaterialReferences(completeMaterialMention(visibleInput, material, materials).trimEnd(), selectedMentions)); textareaRef.current?.focus(); }}>
            {material.title || material.filename || material.id}
          </button>)}
          {!materialSuggestions.length && <span className="theme-text-secondary block px-3 py-2 text-sm">没有匹配的任务论文</span>}
        </div>
      )}
      {skillSuggestions.length > 0 && (
        <div ref={suggestionsRef} className="chat-composer-menu theme-panel theme-border mx-4 rounded-lg border p-1" role="group" aria-label="功能命令">
          {skillSuggestions.map((skill) => (
            <button key={skill.id} type="button" className="theme-text-primary flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm hover:bg-[var(--panel-muted)]"
              onClick={() => { setInputValue(`/${skill.command} ${inputValue.replace(/^\s*\/[^\s]*\s*/u, '')}`); textareaRef.current?.focus(); }}>
              <span>/{skill.command}</span><span className="theme-text-secondary text-xs">{skill.description}</span>
            </button>
          ))}
        </div>
      )}
      <div className="workbench-composer-send">
        {isLoading && onAbortChat && <button type="button" onClick={onAbortChat} className="chat-composer-stop" title="停止生成" aria-label="停止生成"><X size={16} />停止</button>}
        <button type="button" onClick={handleSend} disabled={!visibleInput.trim() || isLoading || submitting} className="reader-chat-send" aria-label={sendLabel} title={sendLabel}>
          {sendLabel !== '发送消息' && <span>{sendLabel}</span>}
          <Send size={18} />
        </button>
      </div>
      </ComposerSurface>
    </div>
  );
};

export default ChatPanel;
