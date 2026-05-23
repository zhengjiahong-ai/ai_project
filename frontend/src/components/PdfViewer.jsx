import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Worker, Viewer } from '@react-pdf-viewer/core';
import { defaultLayoutPlugin } from '@react-pdf-viewer/default-layout';
import { highlightPlugin } from '@react-pdf-viewer/highlight';
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
import '@react-pdf-viewer/default-layout/lib/styles/index.css';
import '@react-pdf-viewer/highlight/lib/styles/index.css';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.js?url';
import { apiService } from '../services/api';
import { buildExplainSelectionPayload } from '../utils/pdfFormulaSelection';
import { buildPageLayout } from '../utils/pdfTranslationLayout.js';
import MarkdownContent from './MarkdownContent';
import { getMessageMarkdownClassName } from './MessageMarkdownRenderer';

const workerUrl = pdfWorkerUrl;
const EXPLAIN_CONTEXT_MAX_CHARS = 4500;
const INLINE_ACTIONS = [
  { id: 'explain', label: '解释', icon: Sparkles },
  { id: 'translate', label: '翻译', icon: Languages },
  { id: 'deconstruct', label: '拆解', icon: FileText },
  { id: 'critique', label: '批判', icon: ShieldAlert },
  { id: 'note', label: '记边注', icon: Bookmark },
];

const trimExplainContext = (text = '') => {
  const trimmed = String(text || '').trim();
  if (trimmed.length <= EXPLAIN_CONTEXT_MAX_CHARS) {
    return trimmed;
  }
  return `${trimmed.slice(0, EXPLAIN_CONTEXT_MAX_CHARS).trimEnd()}\n\n[当前页上下文过长，已截断]`;
};

const createSourceMeta = (highlight) => ({
  sourceAnchorId: highlight.sourceAnchorId,
  sourcePageIndex: highlight.position.pageIndex,
  sourceText: highlight.text,
  sourceActionId: highlight.actionId,
  sourceActionLabel: highlight.actionLabel,
});

const buildInlineActionPayload = (actionId, selectedText, context) => {
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

const InlineContextMenu = ({ selectionRegion, onAction }) => (
  <div
    className="inline-context-menu absolute z-50 flex items-center gap-1.5"
    style={{
      top: `${selectionRegion.top + selectionRegion.height}%`,
      left: `${selectionRegion.left}%`,
      transform: 'translateY(10px)',
    }}
  >
    {INLINE_ACTIONS.map((action) => {
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

export const ExplanationPopup = ({ highlight, onClose, onSubAsk, onDelete, onSaveNote }) => {
  const [query, setQuery] = useState('');

  const handleAsk = () => {
    if (!query.trim() || highlight.isLoading) return;
    onSubAsk(query);
    setQuery('');
  };

  const handleSave = () => {
    const historyToSave = highlight.chatHistory.slice(1);

    let interpretationMarkdown = '';
    if (historyToSave.length === 1 && historyToSave[0].role === 'ai') {
      interpretationMarkdown = historyToSave[0].content;
    } else if (historyToSave.length > 1) {
      interpretationMarkdown = historyToSave
        .map((message) => {
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
      alert('包含追问记录的完整笔记已收藏到“学术笔记”栏目。');
      onClose();
    }
  };

  return (
    <div
      className="theme-popup absolute z-[999] flex max-h-[400px] w-80 flex-col rounded-xl animate-in fade-in zoom-in duration-200"
      style={{
        ...(highlight.position.top > 55
          ? { bottom: `${100 - highlight.position.top}%`, transform: 'translateY(-12px)' }
          : { top: `${highlight.position.top + highlight.position.height}%`, transform: 'translateY(12px)' }),
        left: `min(${highlight.position.left}%, calc(100% - 340px))`,
      }}
    >
      <div className="theme-popup-header flex shrink-0 items-center justify-between rounded-t-xl border-b p-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex items-center gap-1.5 text-xs font-bold text-pixiu">
            <Sparkles size={14} /> {highlight.actionLabel || 'AI 解释'}
          </span>
          <span className="source-link-chip shrink-0">p.{highlight.position.pageIndex + 1}</span>
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
            onClick={onClose}
            className="theme-icon-button rounded-full p-1 transition-colors"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="theme-panel flex-1 overflow-y-auto p-4 text-sm">
        <div className="prose prose-sm flex flex-col gap-4">
          {highlight.chatHistory.map((message, index) => {
            if (index === 0 && message.role === 'user') return null;
            return (
              <div
                key={index}
                className={`rounded-xl p-3 ${
                  message.role === 'user'
                    ? 'theme-markdown-panel theme-border border'
                    : 'theme-card-soft'
                }`}
              >
                <MarkdownContent
                  className={getMessageMarkdownClassName(message.role, 'popup')}
                >
                  {message.content}
                </MarkdownContent>
              </div>
            );
          })}
          {highlight.isLoading && (
            <div className="theme-text-muted flex items-center gap-2 p-2 text-xs italic">
              <Sparkles size={12} className="animate-pulse" /> AI 正在处理中...
            </div>
          )}
        </div>
      </div>

      <div className="theme-popup-footer flex shrink-0 gap-2 rounded-b-xl border-t p-3">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && handleAsk()}
          placeholder="继续追问..."
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

const PdfViewer = ({
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
  const [highlights, setHighlights] = useState([]);
  const [activeHighlightId, setActiveHighlightId] = useState(null);

  const defaultLayoutPluginInstance = defaultLayoutPlugin();
  const pdfDocRef = useRef(null);
  const currentPageRef = useRef(0);
  const isFirstRender = useRef(true);
  const latestPdfIdRef = useRef(pdfId);
  const pageTextByIndexRef = useRef({});
  const initialViewerPage = Number.isFinite(targetPageIndex) ? Math.max(0, targetPageIndex) : 0;
  const viewerKey = `${pdfId || 'empty'}-${initialViewerPage}-${targetPageJumpToken}`;

  useEffect(() => {
    latestPdfIdRef.current = pdfId;
  }, [pdfId]);

  useEffect(() => {
    setActiveHighlightId(null);
    setHighlights(initialHighlights || []);
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

    const targetHighlight = highlights.find((highlight) => highlight.sourceAnchorId === focusedSourceAnchorId);
    if (targetHighlight) {
      setActiveHighlightId(targetHighlight.id);
    }
  }, [focusedSourceAnchorId, focusedSourceAnchorToken, highlights]);

  const extractPageText = useCallback(
    async (pageIndex, doc = pdfDocRef.current) => {
      if (!doc) {
        return;
      }

      const requestedPdfId = latestPdfIdRef.current;

      try {
        const page = await doc.getPage(pageIndex + 1);
        const textContent = await page.getTextContent();
        const viewport = page.getViewport({ scale: 1 });
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
    ({ doc }) => {
      pdfDocRef.current = doc;
      const maxPageIndex = Math.max((doc?.numPages || 1) - 1, 0);
      const initialPageIndex = Number.isFinite(targetPageIndex)
        ? Math.max(0, Math.min(targetPageIndex, maxPageIndex))
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
    (event) => {
      currentPageRef.current = event.currentPage;
      const doc = event.doc || pdfDocRef.current;
      onPageChange?.({
        pageIndex: event.currentPage,
        totalPages: doc?.numPages || 0,
      });
      extractPageText(event.currentPage, event.doc || pdfDocRef.current);
    },
    [extractPageText, onPageChange],
  );

  const syncSelectionMessage = useCallback((content, role, highlight) => {
    onSelection?.(content, role, true, createSourceMeta(highlight));
  }, [onSelection]);

  const handleInitialAsk = useCallback(async (id, requestPayload, pageIndex, context) => {
    try {
      const normalizedResponse = requestPayload.requestKind === 'explain'
        ? await apiService.explainText(requestPayload.requestText, pdfId, pageIndex + 1, context)
        : await apiService.sendMessage(requestPayload.requestText, pdfId, [], paperSkeleton);
      const normalizedContent =
        normalizedResponse?.data?.explanation ??
        normalizedResponse?.explanation ??
        normalizedResponse?.data?.reply ??
        normalizedResponse?.data?.message ??
        normalizedResponse?.reply ??
        normalizedResponse?.message ??
        'No response.';
      let nextHighlight = null;
      setHighlights((prev) =>
        prev.map((highlight) => {
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
      setHighlights((prev) =>
        prev.map((highlight) =>
          highlight.id === id
            ? {
                ...highlight,
                chatHistory: [...highlight.chatHistory, { role: 'ai', content: '抱歉，解释请求失败，请稍后重试。' }],
                isLoading: false,
              }
            : highlight,
        ),
      );
    }
  }, [paperSkeleton, pdfId, syncSelectionMessage]);

  const handleSubAsk = async (id, query) => {
    const highlight = highlights.find((item) => item.id === id);
    if (!highlight || highlight.isLoading) return;

    const newHistory = [...highlight.chatHistory, { role: 'user', content: query }];
    setHighlights((prev) =>
      prev.map((item) => (item.id === id ? { ...item, chatHistory: newHistory, isLoading: true } : item)),
    );

    onSelection?.(query, 'user', true, createSourceMeta(highlight));

    try {
      const backendHistory = newHistory.slice(0, -1).map((message) => ({
        role: message.role === 'ai' ? 'assistant' : 'user',
        content: message.content,
      }));
      const response = await apiService.sendMessage(query, pdfId, backendHistory, paperSkeleton);
      const aiResponse = response?.data?.reply ?? response?.reply ?? response?.message ?? '暂无回复';

      setHighlights((prev) =>
        prev.map((item) =>
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
      setHighlights((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                chatHistory: [...item.chatHistory, { role: 'ai', content: '抱歉，追问失败，请稍后重试。' }],
                isLoading: false,
              }
            : item,
        ),
      );
    }
  };

  const handleSelectionAction = useCallback((actionId, props) => {
    const selectedText = props.selectedText;
    const pageIndex = props.highlightAreas?.[0]?.pageIndex ?? props.selectionRegion?.pageIndex ?? currentPageRef.current;
    const selectionPosition = { ...props.selectionRegion, pageIndex };
    const context = trimExplainContext(pageTextByIndexRef.current[pageIndex] || '');
    const sourceAnchorId = `selection-${Date.now()}`;
    const requestPayload = buildInlineActionPayload(actionId, selectedText, context);
    const id = Date.now();
    const nextHighlight = {
      id,
      sourceAnchorId,
      text: selectedText,
      highlightAreas: props.highlightAreas,
      position: selectionPosition,
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

      setHighlights((prev) => [
        ...prev,
        {
          ...nextHighlight,
          chatHistory: [
            { role: 'ai', content: '已保存为边注笔记。你可以稍后在笔记区查看，也可以继续围绕这一段追问。' },
          ],
        },
      ]);
      setActiveHighlightId(id);
      props.cancel();
      return;
    }

    setHighlights((prev) => [...prev, nextHighlight]);
    setActiveHighlightId(id);
    props.cancel();
    syncSelectionMessage(requestPayload.displayMessage, 'user', nextHighlight);
    handleInitialAsk(id, requestPayload, pageIndex, context);
  }, [handleInitialAsk, onSaveNote, syncSelectionMessage]);

  const highlightPluginInstance = highlightPlugin({
    renderHighlightTarget: (props) =>
      !activeHighlightId ? (
        <InlineContextMenu
          selectionRegion={props.selectionRegion}
          onAction={(actionId) => handleSelectionAction(actionId, props)}
        />
      ) : null,
    renderHighlights: (props) => (
      <div>
        {highlights.map((highlightEntity) => (
          <React.Fragment key={highlightEntity.id}>
            {highlightEntity.highlightAreas
              .filter((area) => area.pageIndex === props.pageIndex)
              .map((area, index) => (
                <div
                  key={index}
                  style={Object.assign(
                    {},
                    {
                      background:
                        activeHighlightId === highlightEntity.id ? 'rgba(77, 0, 153, 0.4)' : 'rgba(77, 0, 153, 0.2)',
                      border:
                        activeHighlightId === highlightEntity.id ? '1px solid rgba(77, 0, 153, 0.6)' : 'none',
                      cursor: 'pointer',
                      mixBlendMode: 'multiply',
                      zIndex: 10,
                      pointerEvents: 'auto',
                    },
                    props.getCssProperties(area, props.rotation),
                  )}
                  onClick={(event) => {
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

  const activeHighlight = activeHighlightId
    ? highlights.find((highlight) => highlight.id === activeHighlightId) || null
    : null;

  return (
    <div className="relative h-full w-full">
      {fileUrl ? (
        <Worker workerUrl={workerUrl}>
          <Viewer
            key={viewerKey}
            fileUrl={fileUrl}
            initialPage={initialViewerPage}
            plugins={[defaultLayoutPluginInstance, highlightPluginInstance]}
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
          onSubAsk={(query) => handleSubAsk(activeHighlight.id, query)}
          onDelete={() => {
            setHighlights((prev) => prev.filter((highlight) => highlight.id !== activeHighlightId));
            setActiveHighlightId(null);
          }}
          onSaveNote={onSaveNote}
        />
      )}
    </div>
  );
};

export default PdfViewer;

