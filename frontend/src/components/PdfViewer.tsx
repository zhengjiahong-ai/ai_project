import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Worker, Viewer, SpecialZoomLevel, type PluginFunctions } from '@react-pdf-viewer/core';
import { highlightPlugin, type RenderHighlightTargetProps, type RenderHighlightsProps } from '@react-pdf-viewer/highlight';
import {
  Bookmark,
  FileText,
  Languages,
  Send,
  ShieldAlert,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';

import '@react-pdf-viewer/core/lib/styles/index.css';
import '@react-pdf-viewer/highlight/lib/styles/index.css';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.js?url';
import { apiService } from '../services/api';
import { buildExplainSelectionPayload } from '../utils/pdfFormulaSelection';
import { focusSelectionContext } from '../utils/selectionContext';
import { buildPageLayout } from '../utils/pdfTranslationLayout.js';
import { recoverMathGlyphs } from '../utils/pdfMathGlyphs.js';
import MarkdownContent from './MarkdownContent';
import { getMessageMarkdownClassName } from './MessageMarkdownRenderer';
import PdfSkeleton from './PdfSkeleton';
import {
  loadHighlights,
  addHighlight,
  deleteHighlight,
} from '../services/highlightStore';

const PdfLoadError = ({ onVisible }: { onVisible: () => void }) => {
  useEffect(onVisible, [onVisible]);
  return <div role="alert" className="theme-empty-state flex h-full items-center justify-center p-6 text-sm">
    这份 PDF 暂时无法打开，请检查文件是否完整或重新上传。
  </div>;
};

// ── Types ──────────────────────────────────────────────────────────────────

interface PdfViewerSelectionRegion {
  top: number;
  left: number;
  height: number;
  width: number;
  pageIndex?: number;
}

interface HighlightArea {
  pageIndex: number;
  top: number;
  left: number;
  width: number;
  height: number;
}

interface PdfViewerHighlightPosition {
  pageIndex: number;
  top: number;
  left: number;
  width: number;
  height: number;
}

interface PdfViewerChatMessage {
  role: 'user' | 'ai' | 'assistant';
  content: string;
}

interface PdfViewerHighlight {
  id: number;
  sourceAnchorId: string;
  text: string;
  position: PdfViewerHighlightPosition;
  highlightAreas: HighlightArea[];
  actionId: string;
  actionLabel: string;
  chatHistory: PdfViewerChatMessage[];
  isLoading: boolean;
  color?: string;
  createdAt?: string;
  anchorId?: string;
  pageNumber?: number;
  sourceActionId?: string;
  sourceActionLabel?: string;
  sourceText?: string;
  sourcePageIndex?: number;
}

interface InlineActionPayload {
  actionLabel: string;
  displayMessage: string;
  requestKind: string;
  requestText: string;
}

interface PageLayoutResult {
  pageText: string;
  pageLayout: unknown;
}

interface PaperSkeleton {
  [key: string]: unknown;
}

interface NotePayload {
  text: string;
  aiInterpretation: string;
  pageNumber: number;
  sourceAnchorId: string;
  sourcePageIndex: number;
  sourceActionId: string;
  sourceActionLabel: string;
}

interface PageChangePayload {
  pageIndex: number;
  totalPages: number;
}

interface PageTextExtractedPayload {
  pageIndex: number;
  pageText: string;
  pageLayout: PageLayoutResult['pageLayout'] | null;
}

interface ApiResponse {
  data?: {
    explanation?: string;
    reply?: string;
    message?: string;
  };
  explanation?: string;
  reply?: string;
  message?: string;
}

// ── Constants ──────────────────────────────────────────────────────────────

const workerUrl: string = pdfWorkerUrl;
const EXPLAIN_CONTEXT_MAX_CHARS: number = 4500;
const SCANNED_OR_LOW_TEXT_STATUS: string = 'scanned_or_low_text';

const HIGHLIGHT_COLORS = [
  { value: 'yellow', hex: '#fef08a', label: '黄色' },
  { value: 'green',  hex: '#bbf7d0', label: '绿色' },
  { value: 'blue',   hex: '#bfdbfe', label: '蓝色' },
  { value: 'pink',   hex: '#fbcfe8', label: '粉色' },
];

interface InlineActionDef {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number }>;
}

const INLINE_ACTIONS: InlineActionDef[] = [
  { id: 'explain', label: '解释', icon: Sparkles },
  { id: 'translate', label: '翻译', icon: Languages },
  { id: 'deconstruct', label: '拆解', icon: FileText },
  { id: 'critique', label: '批判', icon: ShieldAlert },
  { id: 'note', label: '记边注', icon: Bookmark },
];

// ── Helpers ────────────────────────────────────────────────────────────────

const normalizeHighlightRecord = (
  highlight: Record<string, unknown>,
  index: number = 0,
): PdfViewerHighlight | null => {
  if (!highlight || typeof highlight !== 'object') {
    return null;
  }

  const position: Record<string, unknown> =
    highlight.position && typeof highlight.position === 'object' ? (highlight.position as Record<string, unknown>) : {};
  const pageIndex: number = Number.isFinite(position.pageIndex)
    ? (position.pageIndex as number)
    : Number.isFinite(highlight.pageNumber as number)
      ? (highlight.pageNumber as number)
      : 0;
  const sourceAnchorId: string =
    (highlight.sourceAnchorId as string) ||
    (highlight.anchorId as string) ||
    `legacy-highlight-${highlight.id ?? index}`;
  const text: string = typeof highlight.text === 'string' ? (highlight.text as string) : '';
  const normalizedHistory: PdfViewerChatMessage[] =
    Array.isArray(highlight.chatHistory) && highlight.chatHistory.length > 0
      ? (highlight.chatHistory as PdfViewerChatMessage[])
      : text
        ? [{ role: 'ai' as const, content: '历史划线记录' }]
        : [{ role: 'ai' as const, content: '这是历史划线记录。' }];

  return {
    ...(highlight as unknown as Record<string, unknown>),
    id: (highlight.id as number) ?? Date.now() + index,
    sourceAnchorId,
    text,
    position: {
      ...position,
      pageIndex,
      top: Number(position.top) || 0,
      left: Number(position.left) || 0,
      width: Number(position.width) || 0,
      height: Number(position.height) || 0,
    } as PdfViewerHighlightPosition,
    highlightAreas: Array.isArray(highlight.highlightAreas) ? (highlight.highlightAreas as HighlightArea[]) : [],
    actionId: (highlight.actionId as string) || (highlight.sourceActionId as string) || 'legacy',
    actionLabel: (highlight.actionLabel as string) || (highlight.sourceActionLabel as string) || '历史划线',
    chatHistory: normalizedHistory,
    isLoading: Boolean(highlight.isLoading),
  } as PdfViewerHighlight;
};

const normalizeHighlightCollection = (highlights: unknown[] = []): PdfViewerHighlight[] =>
  (Array.isArray(highlights) ? highlights : [])
    .map((highlight: unknown, index: number) => normalizeHighlightRecord(highlight as Record<string, unknown>, index))
    .filter((h: PdfViewerHighlight | null): h is PdfViewerHighlight => h !== null);

const createSourceMeta = (highlight: PdfViewerHighlight) => ({
  sourceAnchorId: highlight.sourceAnchorId,
  sourcePageIndex: highlight.position.pageIndex,
  sourceText: highlight.text,
  sourceActionId: highlight.actionId,
  sourceActionLabel: highlight.actionLabel,
});

const buildInlineActionPayload = (
  actionId: string,
  selectedText: string,
  context: string,
): InlineActionPayload => {
  const explainPayload = buildExplainSelectionPayload(selectedText);
  if (actionId === 'explain') {
    return {
      actionLabel: 'AI 解释',
      displayMessage: explainPayload.displayMessage,
      requestKind: 'explain',
      requestText: explainPayload.explainText,
    };
  }

  if (actionId === 'translate') {
    return {
      actionLabel: '片段翻译',
      displayMessage: `请翻译以下论文片段：${selectedText}`,
      requestKind: 'chat',
      requestText: [
        '请将以下论文片段翻译成中文，并保留公式、符号和术语的准确性。',
        '',
        '【论文片段】',
        selectedText,
        '',
        '【当前页上下文】',
        context || '无',
      ].join('\n'),
    };
  }

  if (actionId === 'deconstruct') {
    return {
      actionLabel: '片段拆解',
      displayMessage: `请拆解以下论文片段：${selectedText}`,
      requestKind: 'chat',
      requestText: [
        '请分层拆解以下论文片段，说明关键术语、论证结构、隐含假设，以及它在全文中的作用。',
        '',
        '【论文片段】',
        selectedText,
        '',
        '【当前页上下文】',
        context || '无',
      ].join('\n'),
    };
  }

  return {
    actionLabel: actionId === 'note' ? '边注' : '批判阅读',
    displayMessage: `请批判性分析以下论文片段：${selectedText}`,
    requestKind: 'chat',
    requestText: [
      '请批判性审视以下论文片段，指出其核心假设、证据强弱、可能漏洞与替代解释。',
      '',
      '【论文片段】',
      selectedText,
      '',
      '【当前页上下文】',
      context || '无',
    ].join('\n'),
  };
};

// ── Sub-components ─────────────────────────────────────────────────────────

interface ScannedPdfSelectionNoticeProps {
  selectionRegion: PdfViewerSelectionRegion;
}

const ScannedPdfSelectionNotice: React.FC<ScannedPdfSelectionNoticeProps> = ({ selectionRegion }) => (
  <div
    className="scanned-pdf-notice absolute z-50 rounded-full px-4 py-2 text-xs font-semibold"
    style={{
      top: `${selectionRegion.top + selectionRegion.height}%`,
      left: `${selectionRegion.left}%`,
      transform: 'translateY(10px)',
    }}
  >
    <span className="theme-text-muted">
      扫描件 PDF，文本选择不可用
    </span>
  </div>
);

interface InlineContextMenuProps {
  selectionRegion: PdfViewerSelectionRegion;
  onAction: (actionId: string) => void;
}

const InlineContextMenu: React.FC<InlineContextMenuProps & { onColorHighlight?: (color: string) => void }> = ({ selectionRegion, onAction, onColorHighlight }) => (
  <div
    className="inline-context-menu absolute z-50 flex items-center gap-1.5"
    style={{
      top: `${selectionRegion.top + selectionRegion.height}%`,
      left: `clamp(8px, ${selectionRegion.left}%, max(8px, calc(100% - 360px)))`,
      width: 'max-content',
      maxWidth: 'min(360px, calc(100% - 16px))',
      flexWrap: 'wrap',
      transform: 'translateY(10px)',
    }}
  >
    {INLINE_ACTIONS.map((action: InlineActionDef) => {
      const Icon = action.icon;
      return (
        <button
          key={action.id}
          type="button"
          onClick={() => onAction(action.id)}
          className="inline-context-button"
          title={action.label}
        >
          <Icon size={14} />
          <span>{action.label}</span>
        </button>
      );
    })}
    {onColorHighlight && <div role="group" aria-label="高亮颜色" style={{ display: 'flex', gap: 6, padding: '4px 8px' }}>
      {HIGHLIGHT_COLORS.map(color => <button key={color.value} type="button" title={color.label}
        onClick={() => onColorHighlight(color.value)}
        style={{ width: 20, height: 20, borderRadius: '50%', backgroundColor: color.hex,
          border: '2px solid #fff', boxShadow: '0 0 0 1px rgba(0,0,0,0.2)', cursor: 'pointer' }} />)}
    </div>}
  </div>
);

interface ExplanationPopupProps {
  highlight: PdfViewerHighlight;
  onClose: () => void;
  onSubAsk: (query: string) => void;
  onDelete: () => void;
  onSaveNote?: (payload: NotePayload) => void | Promise<void>;
}

export const ExplanationPopup: React.FC<ExplanationPopupProps> = ({
  highlight,
  onClose,
  onSubAsk,
  onDelete,
  onSaveNote,
}) => {
  const [query, setQuery] = useState<string>('');
  const [expanded, setExpanded] = useState(false);
  const explanationMessages = highlight.chatHistory.filter(message => message.role !== 'user');
  const explanation = explanationMessages[explanationMessages.length - 1]?.content || '';
  const shortExplanation = explanation.length > 220 ? `${explanation.slice(0, 220)}…` : explanation;
  const canExpand = explanation.length > 220 || highlight.chatHistory.length > 2;
  useEffect(() => { setExpanded(false); setQuery(''); }, [highlight.id]);
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const originalText: string = highlight.text || '暂无选中文本';
  const popupRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<Element | null>(null);

  // Focus management: capture previous focus, move focus into popup, restore on unmount
  useEffect(() => {
    previousFocusRef.current = document.activeElement;
    // Small delay to let the popup render before focusing
    const timer = setTimeout(() => {
      closeButtonRef.current?.focus();
    }, 0);
    return () => {
      clearTimeout(timer);
      // Restore focus to the previously focused element
      previousFocusRef.current instanceof HTMLElement && previousFocusRef.current.focus();
    };
  }, []);

  const handleKeyDown = (event: React.KeyboardEvent): void => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onClose();
    }
  };

  const handleAsk = (): void => {
    if (!query.trim() || highlight.isLoading) return;
    onSubAsk(query);
    setQuery('');
  };

  const handleSave = async (): Promise<void> => {
    if (saving) return;
    const historyToSave: PdfViewerChatMessage[] = highlight.chatHistory.slice(1);

    let interpretationMarkdown: string = '';
    if (historyToSave.length === 1 && historyToSave[0].role === 'ai') {
      interpretationMarkdown = historyToSave[0].content;
    } else if (historyToSave.length > 1) {
      interpretationMarkdown = historyToSave
        .map((message: PdfViewerChatMessage) => {
          if (message.role === 'user') return `> **我的追问**：\n_${message.content}_`;
          return `**AI 解答**：\n${message.content}`;
        })
        .join('\n\n---\n\n');
    }

    if (!interpretationMarkdown.trim()) {
      interpretationMarkdown = '解析中...';
    }

    if (onSaveNote) {
      setSaving(true); setSaveError('');
      try { await onSaveNote({
        text: highlight.text,
        aiInterpretation: interpretationMarkdown,
        pageNumber: highlight.position.pageIndex,
        sourceAnchorId: highlight.sourceAnchorId,
        sourcePageIndex: highlight.position.pageIndex,
        sourceActionId: highlight.actionId,
        sourceActionLabel: highlight.actionLabel,
      });
      onClose();
      } catch (error) { setSaveError((error as Error).message || '保存失败，当前解释仍保留'); }
      finally { setSaving(false); }
    }
  };

  return (
    <div
      ref={popupRef}
      role="dialog"
      aria-label={`${highlight.actionLabel || 'AI 解释'} - p.${highlight.position.pageIndex + 1}`}
      aria-modal="false"
      className="theme-popup pdf-explanation-popup absolute z-[999] flex max-h-[400px] flex-col rounded-xl animate-in fade-in zoom-in duration-200"
      onKeyDown={handleKeyDown}
      style={{
        ...(highlight.position.top > 55
          ? { bottom: `${100 - highlight.position.top}%`, transform: 'translateY(-12px)' }
          : { top: `${highlight.position.top + highlight.position.height}%`, transform: 'translateY(12px)' }),
        width: 'min(320px, calc(100% - 16px))',
        left: `clamp(8px, ${highlight.position.left}%, max(8px, calc(100% - 328px)))`,
      }}
    >
      <div className="theme-popup-header flex shrink-0 items-center justify-between rounded-t-xl border-b p-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="flex items-center gap-1.5 text-xs font-bold text-pixiu">
              <Sparkles size={14} /> {highlight.actionLabel || 'AI 解释'}
            </span>
            <span className="source-link-chip shrink-0">p.{highlight.position.pageIndex + 1}</span>
          </div>
          {highlight.color && (
            <div className="flex items-center gap-1.5 text-[10px] theme-text-muted">
              <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
                backgroundColor: HIGHLIGHT_COLORS.find((c) => c.value === highlight.color)?.hex || '#fef08a',
                border: '1px solid rgba(0,0,0,0.15)' }} />
              <span>{HIGHLIGHT_COLORS.find((c) => c.value === highlight.color)?.label || highlight.color}</span>
              {highlight.createdAt && (<span className="ml-1">{new Date(highlight.createdAt).toLocaleString()}</span>)}
            </div>
          )}
          <div className="theme-text-secondary line-clamp-2 text-[11px] leading-5">
            {originalText}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onSaveNote && (highlight.actionId !== 'note' || highlight.chatHistory.length > 1) && (
            <button
              onClick={handleSave}
              disabled={saving || highlight.isLoading}
              className="rounded bg-pixiu px-2 py-1 text-[10px] text-white transition-colors hover:bg-pixiu-dark"
            >
              {saving ? '保存中…' : '存为笔记'}
            </button>
          )}
          <button
            onClick={onDelete}
            className="theme-danger-button rounded-full p-1 transition-colors"
            title="删除划线"
          >
            <Trash2 size={14} />
          </button>
          <button
            ref={closeButtonRef}
            onClick={onClose}
            className="theme-icon-button rounded-full p-1 transition-colors"
            aria-label="关闭弹窗"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="theme-panel flex-1 overflow-y-auto p-4 text-sm">
        {saveError && <p role="alert" className="mb-3">{saveError}</p>}
        <div className="space-y-4">
          <div className="theme-card-soft rounded-xl p-3" hidden={!expanded}>
            <div className="theme-text-muted mb-2 text-[11px] font-bold uppercase tracking-wide">原文片段</div>
            <MarkdownContent className="theme-text-primary prose prose-sm max-w-none text-sm">
              {originalText}
            </MarkdownContent>
          </div>

          <div className="theme-card-soft rounded-xl p-3">
            <div className="theme-text-muted mb-2 text-[11px] font-bold uppercase tracking-wide">{expanded ? '当前追问链' : '简短解释'}</div>
            {!expanded && <p className="theme-text-primary whitespace-pre-wrap text-sm leading-6">{shortExplanation}</p>}
            {expanded && highlight.chatHistory.map((message: PdfViewerChatMessage, index: number) => {
              if (index === 0 && message.role === 'user') return null;
              return (
                <div
                  key={index}
                  className={`mb-3 rounded-xl p-3 ${
                    message.role === 'user'
                      ? 'theme-markdown-panel theme-border border'
                      : 'theme-card'
                  }`}
                >
                  <div className="mb-2 flex items-center gap-2">
                    <span className={`chat-role-badge ${message.role === 'user' ? 'chat-role-user' : 'chat-role-ai'}`}>
                      {message.role === 'user' ? '你' : 'Pixiu'}
                    </span>
                  </div>
                  <MarkdownContent
                    className={getMessageMarkdownClassName(message.role, 'popup')}
                  >
                    {message.content}
                  </MarkdownContent>
                </div>
              );
            })}
          </div>

          {(canExpand || expanded) && <button type="button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)} className="text-xs text-pixiu">{expanded ? '收起解释' : '展开完整解释'}</button>}
          {highlight.isLoading && (
            <div className="theme-text-muted flex items-center gap-2 p-2 text-xs italic">
              <Sparkles size={12} className="animate-pulse" /> 正在生成...
            </div>
          )}
        </div>
      </div>

      <div className="theme-popup-footer flex shrink-0 gap-2 rounded-b-xl border-t p-3">
        <input
          value={query}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)}
          onKeyDown={(event: React.KeyboardEvent<HTMLInputElement>) => event.key === 'Enter' && handleAsk()}
          placeholder="继续追问当前片段..."
          className="theme-input flex-1 rounded-md px-2 py-1.5 text-xs outline-none"
        />
        <button
          onClick={handleAsk}
          disabled={highlight.isLoading || !query.trim()}
          className="text-pixiu transition-transform hover:scale-110 disabled:opacity-50 disabled:hover:scale-100"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
};

// ── Main component ─────────────────────────────────────────────────────────

interface PdfViewerProps {
  fileUrl: string | null;
  readingKey?: string;
  active?: boolean;
  onSelection?: (content: string, role: string, isSync: boolean, sourceMeta: Record<string, unknown>) => void;
  onSaveNote?: (payload: NotePayload) => void | Promise<void>;
  pdfId?: string;
  paperSkeleton?: PaperSkeleton | null;
  initialHighlights?: unknown[];
  onHighlightsChange?: (highlights: PdfViewerHighlight[]) => void;
  onPageChange?: (payload: PageChangePayload) => void;
  onPageTextExtracted?: (payload: PageTextExtractedPayload) => void;
  targetPageIndex?: number | null;
  targetPageJumpToken?: number;
  focusedSourceAnchorId?: string | null;
  focusedSourceAnchorToken?: number;
  theme?: string;
  parseStatus?: string | null;
  onNarrowScreenChange?: (isNarrow: boolean) => void;
}

const PdfViewer: React.FC<PdfViewerProps> = ({
  fileUrl,
  readingKey,
  active = true,
  onSelection,
  onSaveNote,
  pdfId,
  paperSkeleton = null,
  initialHighlights,
  onHighlightsChange,
  onPageChange,
  onPageTextExtracted,
  targetPageIndex = null,
  targetPageJumpToken = 0,
  focusedSourceAnchorId = null,
  focusedSourceAnchorToken = 0,
  theme = 'light',
  parseStatus = null,
  onNarrowScreenChange,
}) => {
  const readerRef = useRef<HTMLDivElement | null>(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  const pageChangeRef = useRef(onPageChange);
  pageChangeRef.current = onPageChange;
  const positionKey = readingKey || pdfId || fileUrl || 'empty';
  const positionKeyRef = useRef(positionKey);
  positionKeyRef.current = positionKey;
  const savedPosition = useMemo(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(`pdf-reading:${positionKey}`) || 'null');
      return stored && typeof stored === 'object' ? stored : null;
    } catch { return null; }
  }, [positionKey]);
  const readingPositionRef = useRef({ scale: 1, top: 0, left: 0 });
  const restoringPositionRef = useRef(false);
  const persistReadingPosition = useCallback(() => {
    try { localStorage.setItem(`pdf-reading:${positionKey}`, JSON.stringify(readingPositionRef.current)); } catch { /* Reading remains usable without storage. */ }
  }, [positionKey]);
  const [highlights, setHighlights] = useState<PdfViewerHighlight[]>([]);
  const [activeHighlightId, setActiveHighlightId] = useState<number | null>(null);
  const [isPdfLoading, setIsPdfLoading] = useState<boolean>(true);
  const [displayScale, setDisplayScale] = useState(() => Number(savedPosition?.scale) > 0 ? Number(savedPosition.scale) : 1);
  const [pageTextState, setPageTextState] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading');
  const clearPdfLoading = useCallback(() => setIsPdfLoading(false), []);
  const [selectionNoteError, setSelectionNoteError] = useState('');
  const savingSelectionNote = useRef(false);

  const pdfDocRef = useRef<unknown>(null);
  // A cached child can report its document before this parent's passive effects.
  const mountedRef = useRef(true);
  const loadedDocumentRef = useRef<{ fileUrl: string | null; pdfId?: string } | null>(null);
  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false; }; }, []);
  const currentPageRef = useRef<number>(0);
  const isFirstRender = useRef<boolean>(true);
  const latestPdfIdRef = useRef<string | undefined>(pdfId);
  latestPdfIdRef.current = pdfId;
  const pageTextByIndexRef = useRef<Record<number, string>>({});
  const scaleRef = useRef<number>(Number(savedPosition?.scale) > 0 ? Number(savedPosition.scale) : 1);
  const navigationRef = useRef<PluginFunctions | null>(null);
  const navigationPlugin = useMemo(() => ({
    install: (functions: PluginFunctions) => { navigationRef.current = functions; },
    uninstall: () => { navigationRef.current = null; },
  }), []);
  useLayoutEffect(() => {
    readingPositionRef.current = {
      scale: Number(savedPosition?.scale) > 0 ? Number(savedPosition.scale) : 1,
      top: Math.max(0, Number(savedPosition?.top) || 0),
      left: Math.max(0, Number(savedPosition?.left) || 0),
    };
  }, [savedPosition]);
  useEffect(() => {
    setActiveHighlightId(null);
  }, [positionKey, fileUrl, active, targetPageIndex, targetPageJumpToken]);
  const observedJumpRef = useRef({ page: targetPageIndex, token: targetPageJumpToken });
  const pendingJumpRef = useRef(targetPageJumpToken > 0);
  const appliedJumpRef = useRef(targetPageJumpToken > 0 ? null : { page: targetPageIndex, token: targetPageJumpToken });
  useEffect(() => {
    if (observedJumpRef.current.page !== targetPageIndex || observedJumpRef.current.token !== targetPageJumpToken) pendingJumpRef.current = true;
    observedJumpRef.current = { page: targetPageIndex, token: targetPageJumpToken };
    if (pendingJumpRef.current || !active || isPdfLoading || !pdfDocRef.current) return;
    const position = readingPositionRef.current;
    if (!savedPosition && position.top === 0 && position.left === 0 && position.scale === 1) return;
    restoringPositionRef.current = true;
    if (Math.abs(scaleRef.current - position.scale) > 0.001) navigationRef.current?.zoom(position.scale);
    setDisplayScale(position.scale);
    let secondFrame = 0;
    const frame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => {
        const scroller = readerRef.current?.querySelector<HTMLElement>('.rpv-core__inner-pages');
        if (scroller) { scroller.scrollTop = position.top; scroller.scrollLeft = position.left; }
        restoringPositionRef.current = false;
      });
    });
    return () => { cancelAnimationFrame(frame); cancelAnimationFrame(secondFrame); restoringPositionRef.current = false; };
  }, [active, isPdfLoading, savedPosition, positionKey, targetPageIndex, targetPageJumpToken]);
  const initialViewerPage: number = Number.isFinite(targetPageIndex) ? Math.max(0, targetPageIndex as number) : 0;
  const viewerKey: string = pdfId || 'empty';
  useEffect(() => {
    if (!active || isPdfLoading || !pdfDocRef.current || !Number.isFinite(targetPageIndex)) return;
    if (!pendingJumpRef.current && appliedJumpRef.current?.page === targetPageIndex && appliedJumpRef.current?.token === targetPageJumpToken) return;
    pendingJumpRef.current = false;
    appliedJumpRef.current = { page: targetPageIndex, token: targetPageJumpToken };
    const max = Math.max(((pdfDocRef.current as { numPages?: number }).numPages || 1) - 1, 0);
    void navigationRef.current?.jumpToPage(Math.max(0, Math.min(targetPageIndex as number, max)));
  }, [targetPageIndex, targetPageJumpToken, active, isPdfLoading]);

  useEffect(() => {
    latestPdfIdRef.current = pdfId;
  }, [pdfId]);

  useLayoutEffect(() => {
    if (fileUrl && loadedDocumentRef.current?.fileUrl !== fileUrl) {
      setIsPdfLoading(true);
      setDisplayScale(readingPositionRef.current.scale);
      setPageTextState('loading');
    }
  }, [fileUrl]);

  useEffect(() => {
    setActiveHighlightId(null);
    setHighlights(normalizeHighlightCollection(initialHighlights));
    if (loadedDocumentRef.current?.pdfId !== pdfId) {
      pdfDocRef.current = null;
      currentPageRef.current = 0;
      pageTextByIndexRef.current = {};
    }
    // We only want to reset annotations when switching papers, not when parent persistence echoes state back.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdfId]);

  useEffect(() => {
    if (pdfId) {
      let cancelled = false;
      loadHighlights(pdfId).then((saved) => {
        if (cancelled || pdfId !== latestPdfIdRef.current) return;
        if (saved && saved.length > 0) {
          setHighlights(normalizeHighlightCollection(saved));
        }
      });
      return () => { cancelled = true; };
    }
  }, [pdfId]);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }

    if (onHighlightsChange) {
      onHighlightsChange(highlights);
    }
  }, [highlights, onHighlightsChange]);

  useEffect(() => {
    if (!active || !focusedSourceAnchorId) {
      return;
    }

    const targetHighlight: PdfViewerHighlight | undefined = highlights.find(
      (highlight: PdfViewerHighlight) => highlight.sourceAnchorId === focusedSourceAnchorId,
    );
    if (targetHighlight) {
      setActiveHighlightId(targetHighlight.id);
    }
  }, [focusedSourceAnchorId, focusedSourceAnchorToken, highlights, active]);

  // Responsive layout: detect narrow screens (< 1024px) and notify parent
  useEffect(() => {
    if (!onNarrowScreenChange) {
      return;
    }

    const mediaQuery = window.matchMedia('(max-width: 1023px)');

    const handleChange = (event: MediaQueryListEvent | MediaQueryList): void => {
      onNarrowScreenChange(event.matches);
    };

    // Initial check
    handleChange(mediaQuery);

    mediaQuery.addEventListener('change', handleChange);

    return () => {
      mediaQuery.removeEventListener('change', handleChange);
    };
  }, [onNarrowScreenChange]);

  const extractPageText = useCallback(
    async (pageIndex: number, doc: unknown = pdfDocRef.current): Promise<void> => {
      if (!doc) {
        return;
      }

      const requestedPdfId: string | undefined = latestPdfIdRef.current;
      const requestedPositionKey = positionKeyRef.current;

      try {
        const docWithPage = doc as { getPage: (n: number) => Promise<unknown> };
        const page = await docWithPage.getPage(pageIndex + 1);
        const pageWithContent = page as { getTextContent: () => Promise<unknown>; getViewport: (opts: Record<string, number>) => unknown };
        const textContent = await recoverMathGlyphs(page, await pageWithContent.getTextContent(), doc);
        const viewport = pageWithContent.getViewport({ scale: 1 });
        const { pageText, pageLayout } = buildPageLayout(textContent, viewport);

        if (!activeRef.current || requestedPositionKey !== positionKeyRef.current || !mountedRef.current || requestedPdfId !== latestPdfIdRef.current || pageIndex !== currentPageRef.current) {
          return;
        }
        pageTextByIndexRef.current[pageIndex] = pageText;
        setPageTextState(pageText.trim() ? 'ready' : 'empty');
        onPageTextExtracted?.({
          pageIndex,
          pageText,
          pageLayout,
        });
      } catch (error) {
        console.warn(`Failed to extract text for page ${pageIndex + 1}.`, error);
        if (!activeRef.current || requestedPositionKey !== positionKeyRef.current || !mountedRef.current || requestedPdfId !== latestPdfIdRef.current || pageIndex !== currentPageRef.current) {
          return;
        }
        pageTextByIndexRef.current[pageIndex] = '';
        setPageTextState('error');
        onPageTextExtracted?.({
          pageIndex,
          pageText: '',
          pageLayout: null,
        });
      }
    },
    [onPageTextExtracted],
  );

  useEffect(() => {
    if (active && pdfDocRef.current) void extractPageText(currentPageRef.current);
  }, [active, positionKey, extractPageText]);

  const handleDocumentLoad = useCallback(
    ({ doc }: { doc: { numPages?: number } }) => {
      if (!mountedRef.current) return;
      pdfDocRef.current = doc;
      loadedDocumentRef.current = {fileUrl, pdfId};
      const maxPageIndex: number = Math.max((doc?.numPages || 1) - 1, 0);
      const initialPageIndex: number = Number.isFinite(targetPageIndex)
        ? Math.max(0, Math.min(targetPageIndex as number, maxPageIndex))
        : currentPageRef.current;
      currentPageRef.current = initialPageIndex;
      setIsPdfLoading(false);
      if (!activeRef.current) return;
      onPageChange?.({
        pageIndex: initialPageIndex,
        totalPages: doc?.numPages || 0,
      });
      extractPageText(initialPageIndex, doc);
    },
    [extractPageText, onPageChange, targetPageIndex, fileUrl, pdfId],
  );

  const handleViewerPageChange = useCallback(
    (event: { currentPage: number; doc?: { numPages?: number } }) => {
      if (!mountedRef.current || !activeRef.current) return;
      if (event.currentPage !== currentPageRef.current) setActiveHighlightId(null);
      currentPageRef.current = event.currentPage;
      setPageTextState('loading');
      const doc = event.doc || pdfDocRef.current;
      onPageChange?.({
        pageIndex: event.currentPage,
        totalPages: (doc as { numPages?: number })?.numPages || 0,
      });
      extractPageText(event.currentPage, event.doc || pdfDocRef.current);
    },
    [extractPageText, onPageChange],
  );
  useEffect(() => {
    if (!active || isPdfLoading || !pdfDocRef.current) return;
    // A PDF may finish loading while an artifact is restored over it. Its viewer
    // need not emit another page event when revealed, so publish the known count.
    pageChangeRef.current?.({ pageIndex: currentPageRef.current,
      totalPages: (pdfDocRef.current as { numPages?: number }).numPages || 0 });
  }, [active, isPdfLoading, positionKey]);

  const syncSelectionMessage = useCallback(
    (content: string, role: string, highlight: PdfViewerHighlight): void => {
      onSelection?.(content, role, true, createSourceMeta(highlight));
    },
    [onSelection],
  );

  const handleInitialAsk = useCallback(
    async (
      id: number,
      requestPayload: InlineActionPayload,
      pageIndex: number,
      context: string,
    ): Promise<void> => {
      try {
        const apiPdfId: string | null = pdfId ?? null;
        // api.ts parameters have narrow inferred types from defaults; cast needed until api.ts is typed
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const normalizedResponse: ApiResponse = requestPayload.requestKind === 'explain'
          ? await (apiService as any).explainText(requestPayload.requestText, apiPdfId, pageIndex + 1, context)
          : await (apiService as any).sendMessage(requestPayload.requestText, apiPdfId, [], paperSkeleton);
        const normalizedContent: string =
          normalizedResponse?.data?.explanation ??
          normalizedResponse?.explanation ??
          normalizedResponse?.data?.reply ??
          normalizedResponse?.data?.message ??
          normalizedResponse?.reply ??
          normalizedResponse?.message ??
          'No response.';
        let nextHighlight: PdfViewerHighlight | null = null;
        setHighlights((prev: PdfViewerHighlight[]) =>
          prev.map((highlight: PdfViewerHighlight) => {
            if (highlight.id !== id) {
              return highlight;
            }

            nextHighlight = {
              ...highlight,
              chatHistory: [...highlight.chatHistory, { role: 'ai', content: normalizedContent }],
              isLoading: false,
            };
            return nextHighlight;
          }),
        );
        if (nextHighlight) {
          syncSelectionMessage(normalizedContent, 'ai', nextHighlight);
        }
        return;
      } catch {
        setHighlights((prev: PdfViewerHighlight[]) =>
          prev.map((highlight: PdfViewerHighlight) =>
            highlight.id === id
              ? {
                  ...highlight,
                  chatHistory: [
                    ...highlight.chatHistory,
                    { role: 'ai', content: '抱歉，解释请求失败，请稍后重试。' },
                  ],
                  isLoading: false,
                }
              : highlight,
          ),
        );
      }
    },
    [paperSkeleton, pdfId, syncSelectionMessage],
  );

  const handleSubAsk = async (id: number, query: string): Promise<void> => {
    const highlight: PdfViewerHighlight | undefined = highlights.find((item: PdfViewerHighlight) => item.id === id);
    if (!highlight || highlight.isLoading) return;

    const newHistory: PdfViewerChatMessage[] = [...highlight.chatHistory, { role: 'user', content: query }];
    setHighlights((prev: PdfViewerHighlight[]) =>
      prev.map((item: PdfViewerHighlight) => (item.id === id ? { ...item, chatHistory: newHistory, isLoading: true } : item)),
    );

    onSelection?.(query, 'user', true, createSourceMeta(highlight));

    try {
      const backendHistory = newHistory.slice(0, -1).map((message: PdfViewerChatMessage) => ({
        role: message.role === 'ai' ? 'assistant' : 'user',
        content: message.content,
      }));
      const apiPdfId: string | null = pdfId ?? null;
      // api.ts parameters have narrow inferred types from defaults; cast needed until api.ts is typed
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const response: ApiResponse = await (apiService as any).sendMessage(query, apiPdfId, backendHistory, paperSkeleton);
      const aiResponse: string = response?.data?.reply ?? response?.reply ?? response?.message ?? '暂无回复';

      setHighlights((prev: PdfViewerHighlight[]) =>
        prev.map((item: PdfViewerHighlight) =>
          item.id === id
            ? {
                ...item,
                chatHistory: [...item.chatHistory, { role: 'ai', content: aiResponse }],
                isLoading: false,
              }
            : item,
        ),
      );

      onSelection?.(aiResponse, 'ai', true, createSourceMeta(highlight));
    } catch {
      setHighlights((prev: PdfViewerHighlight[]) =>
        prev.map((item: PdfViewerHighlight) =>
          item.id === id
            ? {
                ...item,
                chatHistory: [
                  ...item.chatHistory,
                  { role: 'ai', content: '抱歉，追问失败，请稍后重试。' },
                ],
                isLoading: false,
              }
            : item,
        ),
      );
    }
  };

  const handleSelectionAction = useCallback(
    async (actionId: string, props: Record<string, unknown>): Promise<void> => {
      const selectedText: string = props.selectedText as string;
      const highlightAreas = props.highlightAreas as HighlightArea[] | undefined;
      const selectionRegion = props.selectionRegion as Record<string, number> | undefined;
      const pageIndex: number =
        highlightAreas?.[0]?.pageIndex ?? selectionRegion?.pageIndex ?? currentPageRef.current;
      const selectionPosition: Record<string, number> = {
        ...(selectionRegion || {}),
        pageIndex,
      };
      const context: string = focusSelectionContext(pageTextByIndexRef.current[pageIndex] || '', selectedText, EXPLAIN_CONTEXT_MAX_CHARS);
      const sourceAnchorId: string = `selection-${Date.now()}`;
      const requestPayload: InlineActionPayload = buildInlineActionPayload(actionId, selectedText, context);
      const highlightId: number = Date.now();
      const nextHighlight: PdfViewerHighlight = {
        id: highlightId,
        sourceAnchorId,
        text: selectedText,
        highlightAreas: highlightAreas || [],
        position: selectionPosition as unknown as PdfViewerHighlightPosition,
        actionId,
        actionLabel: requestPayload.actionLabel,
        chatHistory: [{ role: 'user', content: requestPayload.displayMessage }],
        isLoading: actionId !== 'note',
        color: 'yellow',
        createdAt: new Date().toISOString(),
      };

      if (actionId === 'note') {
        if (savingSelectionNote.current) return;
        savingSelectionNote.current = true; setSelectionNoteError('');
        try {
        if (!onSaveNote) throw new Error('当前页面不能保存笔记');
        await onSaveNote({
          text: selectedText,
          aiInterpretation: '已保存为边注，可继续补充自己的观察与问题。',
          pageNumber: pageIndex,
          sourceAnchorId,
          sourcePageIndex: pageIndex,
          sourceActionId: actionId,
          sourceActionLabel: requestPayload.actionLabel,
        });
        if (pdfId !== latestPdfIdRef.current) return;

        setHighlights((prev: PdfViewerHighlight[]) => [
          ...prev,
          {
            ...nextHighlight,
            chatHistory: [
              { role: 'ai', content: '边注已保存。' },
            ],
          },
        ]);
        setActiveHighlightId(highlightId);
        (props.cancel as () => void)();
        } catch (error) { setSelectionNoteError((error as Error).message || '笔记保存失败，选区仍保留，请重试'); }
        finally { savingSelectionNote.current = false; }
        return;
      }

      setHighlights((prev: PdfViewerHighlight[]) => [...prev, nextHighlight]);
      setActiveHighlightId(highlightId);
      (props.cancel as () => void)();
      syncSelectionMessage(requestPayload.displayMessage, 'user', nextHighlight);
      handleInitialAsk(highlightId, requestPayload, pageIndex, context);
    },
    [handleInitialAsk, onSaveNote, syncSelectionMessage, pdfId],
  );

  const handleColorHighlight = useCallback(
    (color: string, props: Record<string, unknown>) => {
      const selectedText = props.selectedText as string;
      const highlightAreas = props.highlightAreas as HighlightArea[] | undefined;
      const selectionRegion = props.selectionRegion as Record<string, number> | undefined;
      const pageIndex: number = highlightAreas?.[0]?.pageIndex ?? selectionRegion?.pageIndex ?? currentPageRef.current;
      const selectionPosition: Record<string, number> = { ...(selectionRegion || {}), pageIndex };
      const sourceAnchorId: string = `highlight-${Date.now()}`;
      const highlightId: number = Date.now();
      const newHighlight: PdfViewerHighlight = {
        id: highlightId, sourceAnchorId, text: selectedText,
        highlightAreas: highlightAreas || [],
        position: selectionPosition as unknown as PdfViewerHighlightPosition,
        actionId: 'highlight', actionLabel: '高亮标记',
        color, createdAt: new Date().toISOString(),
        chatHistory: [{ role: 'ai' as const, content: '文本高亮标记' }],
        isLoading: false,
      };
      setHighlights((prev: PdfViewerHighlight[]) => [...prev, newHighlight]);
      (props.cancel as () => void)();
      if (pdfId) { addHighlight(pdfId, newHighlight); }
    },
    [pdfId],
  );

  // highlightPlugin has return-type mismatch with React 19 JSX.Element
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const highlightPluginInstance = (highlightPlugin as any)({
    renderHighlightTarget: (props: RenderHighlightTargetProps) => {
      if (parseStatus === SCANNED_OR_LOW_TEXT_STATUS) {
        return (
          <ScannedPdfSelectionNotice
            selectionRegion={props.selectionRegion}
          />
        );
      }

      return !activeHighlightId ? (
          <InlineContextMenu
            selectionRegion={props.selectionRegion}
            onAction={(actionId: string) => handleSelectionAction(actionId, props as unknown as Record<string, unknown>)}
            onColorHighlight={(color: string) => handleColorHighlight(color, props as unknown as Record<string, unknown>)}
          />
      ) : null;
    },
    renderHighlights: (props: RenderHighlightsProps) => (
      <div>
        {highlights.map((highlightEntity: PdfViewerHighlight) => (
          <React.Fragment key={highlightEntity.id}>
            {highlightEntity.highlightAreas
              .filter((area: HighlightArea) => area.pageIndex === props.pageIndex)
              .map((area: HighlightArea, index: number) => {
                // Adjust highlight area based on current scale and rotation
                // Scale factor compensates for pixel-level alignment differences
                // at various zoom levels, while rotation is handled by getCssProperties.
                const currentScale = scaleRef.current || 1;
                const scaleAdjustment: number = 1 + (currentScale - 1) * 0.002;
                const adjustedArea: HighlightArea =
                  Math.abs(currentScale - 1) > 0.001
                    ? {
                        ...area,
                        top: area.top * scaleAdjustment,
                        left: area.left * scaleAdjustment,
                        width: area.width * scaleAdjustment,
                        height: area.height * scaleAdjustment,
                      }
                    : area;

                const colorHex = HIGHLIGHT_COLORS.find((c) => c.value === (highlightEntity.color || 'yellow'))?.hex || '#fef08a';

                return (
                  <div
                    key={index}
                    role="button"
                    tabIndex={0}
                    aria-label={`查看划线解释：${highlightEntity.text.slice(0, 60)}`}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        setActiveHighlightId(highlightEntity.id);
                      }
                    }}
                    style={Object.assign(
                      {},
                      {
                        background: colorHex,
                        opacity: activeHighlightId === highlightEntity.id ? 0.5 : 0.25,
                        border:
                          activeHighlightId === highlightEntity.id
                            ? `1px solid ${colorHex}`
                            : 'none',
                        cursor: 'pointer',
                        mixBlendMode: 'multiply' as const,
                        zIndex: 10,
                        pointerEvents: 'auto' as const,
                      },
                      props.getCssProperties(adjustedArea, props.rotation),
                    )}
                    onClick={(event: React.MouseEvent) => {
                      event.stopPropagation();
                      event.preventDefault();
                      setActiveHighlightId(highlightEntity.id);
                    }}
                  />
                );
              })}
          </React.Fragment>
        ))}
      </div>
    ),
  });

  const activeHighlight: PdfViewerHighlight | null = activeHighlightId !== null
    ? highlights.find((highlight: PdfViewerHighlight) => highlight.id === activeHighlightId) || null
    : null;

  return (
    <div ref={readerRef} className="relative flex h-full w-full flex-col" onScrollCapture={(event) => {
      if (!activeRef.current || restoringPositionRef.current) return;
      const node = event.target as HTMLElement;
      if (!node.classList.contains('rpv-core__inner-pages')) return;
      readingPositionRef.current = { ...readingPositionRef.current, top: node.scrollTop, left: node.scrollLeft };
      persistReadingPosition();
    }}>
      {selectionNoteError && <div role="alert" className="absolute bottom-3 left-3 right-3 z-50 rounded theme-panel p-3 text-sm">{selectionNoteError}</div>}
      {fileUrl ? (
        <>
          <div role="group" aria-label="原文缩放" className="theme-panel flex shrink-0 items-center justify-end gap-2 border-b px-2 py-1 text-xs">
            <button type="button" aria-label="缩小原文" className="rounded px-2 py-1 focus-visible:outline" disabled={isPdfLoading || !pdfDocRef.current || displayScale <= 0.25}
              onClick={() => navigationRef.current?.zoom(Math.max(0.25, displayScale / 1.25))}>−</button>
            <span aria-label="原文缩放比例">{Math.round(displayScale * 100)}%</span>
            <button type="button" aria-label="放大原文" className="rounded px-2 py-1 focus-visible:outline" disabled={isPdfLoading || !pdfDocRef.current || displayScale >= 4}
              onClick={() => navigationRef.current?.zoom(Math.min(4, displayScale * 1.25))}>＋</button>
            <button type="button" className="rounded px-2 py-1 focus-visible:outline" disabled={isPdfLoading || !pdfDocRef.current}
              onClick={() => navigationRef.current?.zoom(SpecialZoomLevel.PageWidth)}>适合宽度</button>
          </div>
          {!isPdfLoading && ['empty','error'].includes(pageTextState) && <p role="status" className="theme-panel shrink-0 px-3 py-2 text-xs theme-text-secondary">
            {pageTextState === 'empty' ? '当前页没有可选文字，可先看原图；划词与文字翻译暂不可用。' : '当前页文字暂不可读取，可继续看原图。'}
          </p>}
          {isPdfLoading && <div className="pointer-events-none absolute inset-x-0 bottom-0 top-9 z-10"><PdfSkeleton /></div>}
          <div className="min-h-0 flex-1" style={{ visibility: isPdfLoading ? 'hidden' : 'visible', width: '100%' }}>
            <Worker workerUrl={workerUrl}>
              <Viewer
                key={viewerKey}
                fileUrl={fileUrl}
                enableSmoothScroll={false}
                initialPage={initialViewerPage}
                defaultScale={Number(savedPosition?.scale) > 0 ? Number(savedPosition.scale) : SpecialZoomLevel.PageWidth}
                plugins={[highlightPluginInstance, navigationPlugin]}
                theme={theme}
                onDocumentLoad={handleDocumentLoad}
                onPageChange={handleViewerPageChange}
                renderError={() => <PdfLoadError onVisible={clearPdfLoading} />}
                onZoom={(event: { scale: number }) => {
                  scaleRef.current = event.scale;
                  if (!activeRef.current) return;
                  if (!restoringPositionRef.current) {
                    readingPositionRef.current = { ...readingPositionRef.current, scale: event.scale };
                    persistReadingPosition();
                  }
                  setDisplayScale(event.scale);
                }}
              />
            </Worker>
          </div>
        </>
      ) : (
        <div className="theme-empty-state flex h-full flex-col items-center justify-center">
          <p>暂无预览内容</p>
        </div>
      )}

      {active && activeHighlight && (
        <ExplanationPopup
          highlight={activeHighlight}
          onClose={() => setActiveHighlightId(null)}
          onSubAsk={(query: string) => handleSubAsk(activeHighlight.id, query)}
          onDelete={() => {
            const highlightToDelete = highlights.find((h: PdfViewerHighlight) => h.id === activeHighlightId);
            if (highlightToDelete && pdfId) {
              const sourceAnchorId: string = highlightToDelete.sourceAnchorId || String(highlightToDelete.id);
              deleteHighlight(pdfId, sourceAnchorId);
            }
            setHighlights((prev: PdfViewerHighlight[]) =>
              prev.filter((highlight: PdfViewerHighlight) => highlight.id !== activeHighlightId),
            );
            setActiveHighlightId(null);
          }}
          onSaveNote={onSaveNote}
        />
      )}
    </div>
  );
};

export default PdfViewer;
