import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Worker, Viewer } from '@react-pdf-viewer/core';
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
import { buildPageLayout } from '../utils/pdfTranslationLayout.js';
import MarkdownContent from './MarkdownContent';
import { getMessageMarkdownClassName } from './MessageMarkdownRenderer';

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

const trimExplainContext = (text: string = ''): string => {
  const trimmed: string = String(text || '').trim();
  if (trimmed.length <= EXPLAIN_CONTEXT_MAX_CHARS) {
    return trimmed;
  }
  return `${trimmed.slice(0, EXPLAIN_CONTEXT_MAX_CHARS).trimEnd()}\n\n[当前页上下文过长，已截断]`;
};

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
        ? [{ role: 'ai' as const, content: '这是历史划线记录。你可以继续围绕这段内容追问。' }]
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

interface InlineContextMenuProps {
  selectionRegion: PdfViewerSelectionRegion;
  onAction: (actionId: string) => void;
}

const InlineContextMenu: React.FC<InlineContextMenuProps> = ({ selectionRegion, onAction }) => (
  <div
    className="inline-context-menu absolute z-50 flex items-center gap-1.5"
    style={{
      top: `${selectionRegion.top + selectionRegion.height}%`,
      left: `${selectionRegion.left}%`,
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
  </div>
);

interface ExplanationPopupProps {
  highlight: PdfViewerHighlight;
  onClose: () => void;
  onSubAsk: (query: string) => void;
  onDelete: () => void;
  onSaveNote?: (payload: NotePayload) => void;
}

export const ExplanationPopup: React.FC<ExplanationPopupProps> = ({
  highlight,
  onClose,
  onSubAsk,
  onDelete,
  onSaveNote,
}) => {
  const [query, setQuery] = useState<string>('');
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

  const handleSave = (): void => {
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
      onSaveNote({
        text: highlight.text,
        aiInterpretation: interpretationMarkdown,
        pageNumber: highlight.position.pageIndex,
        sourceAnchorId: highlight.sourceAnchorId,
        sourcePageIndex: highlight.position.pageIndex,
        sourceActionId: highlight.actionId,
        sourceActionLabel: highlight.actionLabel,
      });
      alert('包含追问记录的完整笔记已收藏到"学术笔记"栏目。');
      onClose();
    }
  };

  return (
    <div
      ref={popupRef}
      role="dialog"
      aria-label={`${highlight.actionLabel || 'AI 解释'} - p.${highlight.position.pageIndex + 1}`}
      aria-modal="true"
      className="theme-popup absolute z-[999] flex max-h-[400px] w-80 flex-col rounded-xl animate-in fade-in zoom-in duration-200"
      onKeyDown={handleKeyDown}
      style={{
        ...(highlight.position.top > 55
          ? { bottom: `${100 - highlight.position.top}%`, transform: 'translateY(-12px)' }
          : { top: `${highlight.position.top + highlight.position.height}%`, transform: 'translateY(12px)' }),
        left: `min(${highlight.position.left}%, calc(100% - 340px))`,
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
          <div className="theme-text-secondary line-clamp-2 text-[11px] leading-5">
            {originalText}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onSaveNote && (
            <button
              onClick={handleSave}
              className="rounded bg-pixiu px-2 py-1 text-[10px] text-white transition-colors hover:bg-pixiu-dark"
            >
              存为笔记
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
        <div className="space-y-4">
          <div className="theme-card-soft rounded-xl p-3">
            <div className="theme-text-muted mb-2 text-[11px] font-bold uppercase tracking-wide">原文片段</div>
            <MarkdownContent className="theme-text-primary prose prose-sm max-w-none text-sm">
              {originalText}
            </MarkdownContent>
          </div>

          <div className="theme-card-soft rounded-xl p-3">
            <div className="theme-text-muted mb-2 text-[11px] font-bold uppercase tracking-wide">当前追问链</div>
            {highlight.chatHistory.map((message: PdfViewerChatMessage, index: number) => {
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

          {highlight.isLoading && (
            <div className="theme-text-muted flex items-center gap-2 p-2 text-xs italic">
              <Sparkles size={12} className="animate-pulse" /> AI 正在先整理一句结论，再补充关键依据...
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
  onSelection?: (content: string, role: string, isSync: boolean, sourceMeta: Record<string, unknown>) => void;
  onSaveNote?: (payload: NotePayload) => void;
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
}

const PdfViewer: React.FC<PdfViewerProps> = ({
  fileUrl,
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
}) => {
  const [highlights, setHighlights] = useState<PdfViewerHighlight[]>([]);
  const [activeHighlightId, setActiveHighlightId] = useState<number | null>(null);

  const pdfDocRef = useRef<unknown>(null);
  const currentPageRef = useRef<number>(0);
  const isFirstRender = useRef<boolean>(true);
  const latestPdfIdRef = useRef<string | undefined>(pdfId);
  const pageTextByIndexRef = useRef<Record<number, string>>({});
  const initialViewerPage: number = Number.isFinite(targetPageIndex) ? Math.max(0, targetPageIndex as number) : 0;
  const viewerKey: string = `${pdfId || 'empty'}-${initialViewerPage}-${targetPageJumpToken}`;

  useEffect(() => {
    latestPdfIdRef.current = pdfId;
  }, [pdfId]);

  useEffect(() => {
    setActiveHighlightId(null);
    setHighlights(normalizeHighlightCollection(initialHighlights));
    pdfDocRef.current = null;
    currentPageRef.current = 0;
    pageTextByIndexRef.current = {};
    // We only want to reset annotations when switching papers, not when parent persistence echoes state back.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    if (!focusedSourceAnchorId) {
      return;
    }

    const targetHighlight: PdfViewerHighlight | undefined = highlights.find(
      (highlight: PdfViewerHighlight) => highlight.sourceAnchorId === focusedSourceAnchorId,
    );
    if (targetHighlight) {
      setActiveHighlightId(targetHighlight.id);
    }
  }, [focusedSourceAnchorId, focusedSourceAnchorToken, highlights]);

  const extractPageText = useCallback(
    async (pageIndex: number, doc: unknown = pdfDocRef.current): Promise<void> => {
      if (!doc) {
        return;
      }

      const requestedPdfId: string | undefined = latestPdfIdRef.current;

      try {
        const docWithPage = doc as { getPage: (n: number) => Promise<unknown> };
        const page = await docWithPage.getPage(pageIndex + 1);
        const pageWithContent = page as { getTextContent: () => Promise<unknown>; getViewport: (opts: Record<string, number>) => unknown };
        const textContent = await pageWithContent.getTextContent();
        const viewport = pageWithContent.getViewport({ scale: 1 });
        const { pageText, pageLayout } = buildPageLayout(textContent, viewport);

        if (requestedPdfId !== latestPdfIdRef.current) {
          return;
        }
        pageTextByIndexRef.current[pageIndex] = pageText;
        onPageTextExtracted?.({
          pageIndex,
          pageText,
          pageLayout,
        });
      } catch (error) {
        console.warn(`Failed to extract text for page ${pageIndex + 1}.`, error);
        if (requestedPdfId !== latestPdfIdRef.current) {
          return;
        }
        pageTextByIndexRef.current[pageIndex] = '';
        onPageTextExtracted?.({
          pageIndex,
          pageText: '',
          pageLayout: null,
        });
      }
    },
    [onPageTextExtracted],
  );

  const handleDocumentLoad = useCallback(
    ({ doc }: { doc: { numPages?: number } }) => {
      pdfDocRef.current = doc;
      const maxPageIndex: number = Math.max((doc?.numPages || 1) - 1, 0);
      const initialPageIndex: number = Number.isFinite(targetPageIndex)
        ? Math.max(0, Math.min(targetPageIndex as number, maxPageIndex))
        : currentPageRef.current;
      currentPageRef.current = initialPageIndex;
      onPageChange?.({
        pageIndex: initialPageIndex,
        totalPages: doc?.numPages || 0,
      });
      extractPageText(initialPageIndex, doc);
    },
    [extractPageText, onPageChange, targetPageIndex],
  );

  const handleViewerPageChange = useCallback(
    (event: { currentPage: number; doc?: { numPages?: number } }) => {
      currentPageRef.current = event.currentPage;
      const doc = event.doc || pdfDocRef.current;
      onPageChange?.({
        pageIndex: event.currentPage,
        totalPages: (doc as { numPages?: number })?.numPages || 0,
      });
      extractPageText(event.currentPage, event.doc || pdfDocRef.current);
    },
    [extractPageText, onPageChange],
  );

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
    (actionId: string, props: Record<string, unknown>): void => {
      const selectedText: string = props.selectedText as string;
      const highlightAreas = props.highlightAreas as HighlightArea[] | undefined;
      const selectionRegion = props.selectionRegion as Record<string, number> | undefined;
      const pageIndex: number =
        highlightAreas?.[0]?.pageIndex ?? selectionRegion?.pageIndex ?? currentPageRef.current;
      const selectionPosition: Record<string, number> = {
        ...(selectionRegion || {}),
        pageIndex,
      };
      const context: string = trimExplainContext(pageTextByIndexRef.current[pageIndex] || '');
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
      };

      if (actionId === 'note') {
        onSaveNote?.({
          text: selectedText,
          aiInterpretation: '已保存为边注，可继续补充自己的观察与问题。',
          pageNumber: pageIndex,
          sourceAnchorId,
          sourcePageIndex: pageIndex,
          sourceActionId: actionId,
          sourceActionLabel: requestPayload.actionLabel,
        });

        setHighlights((prev: PdfViewerHighlight[]) => [
          ...prev,
          {
            ...nextHighlight,
            chatHistory: [
              { role: 'ai', content: '已保存为边注笔记。你可以稍后在笔记区查看，也可以继续围绕这一段追问。' },
            ],
          },
        ]);
        setActiveHighlightId(highlightId);
        (props.cancel as () => void)();
        return;
      }

      setHighlights((prev: PdfViewerHighlight[]) => [...prev, nextHighlight]);
      setActiveHighlightId(highlightId);
      (props.cancel as () => void)();
      syncSelectionMessage(requestPayload.displayMessage, 'user', nextHighlight);
      handleInitialAsk(highlightId, requestPayload, pageIndex, context);
    },
    [handleInitialAsk, onSaveNote, syncSelectionMessage],
  );

  // highlightPlugin has return-type mismatch with React 19 JSX.Element
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const highlightPluginInstance = (highlightPlugin as any)({
    renderHighlightTarget: (props: RenderHighlightTargetProps) =>
      !activeHighlightId ? (
        <InlineContextMenu
          selectionRegion={props.selectionRegion}
          onAction={(actionId: string) => handleSelectionAction(actionId, props as unknown as Record<string, unknown>)}
        />
      ) : null,
    renderHighlights: (props: RenderHighlightsProps) => (
      <div>
        {highlights.map((highlightEntity: PdfViewerHighlight) => (
          <React.Fragment key={highlightEntity.id}>
            {highlightEntity.highlightAreas
              .filter((area: HighlightArea) => area.pageIndex === props.pageIndex)
              .map((area: HighlightArea, index: number) => (
                <div
                  key={index}
                  style={Object.assign(
                    {},
                    {
                      background:
                        activeHighlightId === highlightEntity.id
                          ? 'rgba(77, 0, 153, 0.4)'
                          : 'rgba(77, 0, 153, 0.2)',
                      border:
                        activeHighlightId === highlightEntity.id
                          ? '1px solid rgba(77, 0, 153, 0.6)'
                          : 'none',
                      cursor: 'pointer',
                      mixBlendMode: 'multiply' as const,
                      zIndex: 10,
                      pointerEvents: 'auto' as const,
                    },
                    props.getCssProperties(area, props.rotation),
                  )}
                  onClick={(event: React.MouseEvent) => {
                    event.stopPropagation();
                    event.preventDefault();
                    setActiveHighlightId(highlightEntity.id);
                  }}
                />
              ))}
          </React.Fragment>
        ))}
      </div>
    ),
  });

  const activeHighlight: PdfViewerHighlight | null = activeHighlightId !== null
    ? highlights.find((highlight: PdfViewerHighlight) => highlight.id === activeHighlightId) || null
    : null;

  return (
    <div className="relative h-full w-full">
      {fileUrl ? (
        <Worker workerUrl={workerUrl}>
          <Viewer
            key={viewerKey}
            fileUrl={fileUrl}
            initialPage={initialViewerPage}
            plugins={[highlightPluginInstance]}
            theme={theme}
            onDocumentLoad={handleDocumentLoad}
            onPageChange={handleViewerPageChange}
          />
        </Worker>
      ) : (
        <div className="theme-empty-state flex h-full flex-col items-center justify-center">
          <p>暂无预览内容</p>
        </div>
      )}

      {activeHighlight && (
        <ExplanationPopup
          highlight={activeHighlight}
          onClose={() => setActiveHighlightId(null)}
          onSubAsk={(query: string) => handleSubAsk(activeHighlight.id, query)}
          onDelete={() => {
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
