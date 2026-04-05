import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Worker, Viewer } from '@react-pdf-viewer/core';
import { defaultLayoutPlugin } from '@react-pdf-viewer/default-layout';
import { highlightPlugin } from '@react-pdf-viewer/highlight';
import { Send, Sparkles, Trash2, X } from 'lucide-react';

import '@react-pdf-viewer/core/lib/styles/index.css';
import '@react-pdf-viewer/default-layout/lib/styles/index.css';
import '@react-pdf-viewer/highlight/lib/styles/index.css';
import { apiService } from '../services/api';
import { buildExplainSelectionPayload } from '../utils/pdfFormulaSelection';
import MarkdownContent from './MarkdownContent';

const workerUrl = 'https://unpkg.com/pdfjs-dist@3.4.120/build/pdf.worker.min.js';

const normalizeTextItems = (items = []) =>
  items
    .filter((item) => typeof item?.str === 'string' && item.str.trim())
    .map((item) => ({
      text: item.str.replace(/\s+/g, ' ').trim(),
      x: Number(item.transform?.[4] || 0),
      y: Number(item.transform?.[5] || 0),
    }))
    .filter((item) => item.text);

const buildPageText = (textContent) => {
  const items = normalizeTextItems(textContent?.items);
  if (items.length === 0) {
    return '';
  }

  const sortedItems = [...items].sort((left, right) => {
    if (Math.abs(left.y - right.y) > 2.5) {
      return right.y - left.y;
    }
    return left.x - right.x;
  });

  const lines = [];
  sortedItems.forEach((item) => {
    const currentLine = lines[lines.length - 1];
    if (!currentLine || Math.abs(currentLine.y - item.y) > 3.5) {
      lines.push({ y: item.y, items: [item] });
      return;
    }
    currentLine.items.push(item);
  });

  const segments = [];
  lines.forEach((line, index) => {
    const sortedLineItems = [...line.items].sort((left, right) => left.x - right.x);
    const lineText = sortedLineItems
      .map((item, itemIndex) => {
        if (itemIndex === 0) {
          return item.text;
        }

        const previous = sortedLineItems[itemIndex - 1];
        const horizontalGap = item.x - previous.x;
        return horizontalGap > 10 ? ` ${item.text}` : item.text;
      })
      .join('')
      .trim();

    if (!lineText) {
      return;
    }

    segments.push(lineText);

    const nextLine = lines[index + 1];
    if (nextLine && Math.abs(line.y - nextLine.y) > 14) {
      segments.push('');
    }
  });

  return segments.join('\n').replace(/\n{3,}/g, '\n\n').trim();
};

const ExplanationPopup = ({ highlight, onClose, onSubAsk, onDelete, onSaveNote }) => {
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
          if (message.role === 'user') return `> **我的追问**：_${message.content}_`;
          return `**AI 解答**：\n${message.content}`;
        })
        .join('\n\n---\n\n');
    }

    if (!interpretationMarkdown.trim()) {
      interpretationMarkdown = '解析�?..';
    }

    if (onSaveNote) {
      onSaveNote({
        text: highlight.text,
        aiInterpretation: interpretationMarkdown,
        pageNumber: highlight.position.pageIndex,
      });
      alert("包含追问记录的完整笔记已收藏至‘学术笔记’栏目！");
      onClose();
    }
  };

  return (
    <div
      className="absolute z-[999] flex max-h-[400px] w-80 flex-col rounded-xl border border-blue-100 bg-white shadow-2xl animate-in fade-in zoom-in duration-200"
      style={{
        ...(highlight.position.top > 55
          ? { bottom: `${100 - highlight.position.top}%`, transform: 'translateY(-12px)' }
          : { top: `${highlight.position.top + highlight.position.height}%`, transform: 'translateY(12px)' }),
        left: `min(${highlight.position.left}%, calc(100% - 340px))`,
      }}
    >
      <div className="flex shrink-0 items-center justify-between rounded-t-xl border-b bg-blue-50/50 p-3">
        <span className="flex items-center gap-1.5 text-xs font-bold text-pixiu">
          <Sparkles size={14} /> AI 解释
        </span>
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
            className="rounded-full p-1 text-red-400 transition-colors hover:bg-red-50 hover:text-red-600"
            title="删除划线"
          >
            <Trash2 size={14} />
          </button>
          <button
            onClick={onClose}
            className="rounded-full p-1 text-slate-400 transition-colors hover:bg-slate-200/50 hover:text-slate-600"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto bg-white p-4 text-sm">
        <div className="prose prose-sm flex flex-col gap-4">
          {highlight.chatHistory.map((message, index) => {
            if (index === 0 && message.role === 'user') return null;
            return (
              <div
                key={index}
                className={`rounded-xl p-3 ${
                  message.role === 'user'
                    ? 'border border-pixiu/10 bg-pixiu/5 text-slate-800'
                    : 'bg-slate-50 text-slate-700'
                }`}
              >
                <MarkdownContent>{message.content}</MarkdownContent>
              </div>
            );
          })}
          {highlight.isLoading && (
            <div className="flex items-center gap-2 p-2 text-xs italic text-slate-400">
              <Sparkles size={12} className="animate-pulse" /> AI 正在思�?..
            </div>
          )}
        </div>
      </div>

      <div className="flex shrink-0 gap-2 rounded-b-xl border-t bg-slate-50 p-3">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && handleAsk()}
          placeholder="继续追问..."
          className="flex-1 rounded-md border px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-pixiu/20"
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
  initialHighlights,
  onHighlightsChange,
  onPageChange,
  onPageTextExtracted,
}) => {
  const [highlights, setHighlights] = useState([]);
  const [activeHighlightId, setActiveHighlightId] = useState(null);

  const defaultLayoutPluginInstance = defaultLayoutPlugin();
  const pdfDocRef = useRef(null);
  const currentPageRef = useRef(0);
  const isFirstRender = useRef(true);
  const latestPdfIdRef = useRef(pdfId);

  useEffect(() => {
    latestPdfIdRef.current = pdfId;
  }, [pdfId]);

  useEffect(() => {
    setActiveHighlightId(null);
    setHighlights(initialHighlights || []);
    pdfDocRef.current = null;
    currentPageRef.current = 0;
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

  const extractPageText = useCallback(
    async (pageIndex, doc = pdfDocRef.current) => {
      if (!doc || !onPageTextExtracted) {
        return;
      }

      const requestedPdfId = latestPdfIdRef.current;

      try {
        const page = await doc.getPage(pageIndex + 1);
        const textContent = await page.getTextContent();
        if (requestedPdfId !== latestPdfIdRef.current) {
          return;
        }
        onPageTextExtracted({
          pageIndex,
          pageText: buildPageText(textContent),
        });
      } catch (error) {
        console.warn(`Failed to extract text for page ${pageIndex + 1}.`, error);
        if (requestedPdfId !== latestPdfIdRef.current) {
          return;
        }
        onPageTextExtracted({
          pageIndex,
          pageText: '',
        });
      }
    },
    [onPageTextExtracted],
  );

  const handleDocumentLoad = useCallback(
    ({ doc }) => {
      pdfDocRef.current = doc;
      onPageChange?.(currentPageRef.current);
      extractPageText(currentPageRef.current, doc);
    },
    [extractPageText, onPageChange],
  );

  const handleViewerPageChange = useCallback(
    (event) => {
      currentPageRef.current = event.currentPage;
      onPageChange?.(event.currentPage);
      extractPageText(event.currentPage, event.doc || pdfDocRef.current);
    },
    [extractPageText, onPageChange],
  );

  const handleInitialAsk = async (id, promptText) => {
    try {
      const normalizedResponse = await apiService.sendMessage(promptText, pdfId);
      const normalizedContent =
        normalizedResponse?.data?.reply ?? normalizedResponse?.reply ?? normalizedResponse?.message ?? 'No response.';
      setHighlights((prev) =>
        prev.map((highlight) =>
          highlight.id === id
            ? {
                ...highlight,
                chatHistory: [...highlight.chatHistory, { role: 'ai', content: normalizedContent }],
                isLoading: false,
              }
            : highlight,
        ),
      );
      if (onSelection) {
        onSelection(normalizedContent, 'ai', true);
      }
      return;

    } catch {
      setHighlights((prev) =>
        prev.map((highlight) =>
          highlight.id === id
            ? {
                ...highlight,
                chatHistory: [...highlight.chatHistory, { role: 'ai', content: 'Sorry, the explanation request failed.' }],
                isLoading: false,
              }
            : highlight,
        ),
      );
    }
  };

  const handleSubAsk = async (id, query) => {
    const highlight = highlights.find((item) => item.id === id);
    if (!highlight || highlight.isLoading) return;

    const newHistory = [...highlight.chatHistory, { role: 'user', content: query }];
    setHighlights((prev) =>
      prev.map((item) => (item.id === id ? { ...item, chatHistory: newHistory, isLoading: true } : item)),
    );

    if (onSelection) onSelection(query, 'user', true);

    try {
      const backendHistory = newHistory.slice(0, -1).map((message) => ({
        role: message.role === 'ai' ? 'assistant' : 'user',
        content: message.content,
      }));
      const response = await apiService.sendMessage(query, pdfId, backendHistory);
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

      if (onSelection) onSelection(aiResponse, 'ai', true);
    } catch {
      setHighlights((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                chatHistory: [...item.chatHistory, { role: 'ai', content: 'Sorry, the follow-up request failed.' }],
                isLoading: false,
              }
            : item,
        ),
      );
    }
  };

  const highlightPluginInstance = highlightPlugin({
    renderHighlightTarget: (props) => (
      <div
        className="absolute z-50 flex"
        style={{
          top: `${props.selectionRegion.top + props.selectionRegion.height}%`,
          left: `${props.selectionRegion.left}%`,
          transform: 'translateY(10px)',
        }}
      >
        {!activeHighlightId && (
          <button
            onClick={() => {
              const selectedText = props.selectedText;
              const selectionPayload = buildExplainSelectionPayload(selectedText);
              const id = Date.now();

              setHighlights((prev) => [
                ...prev,
                {
                  id,
                  text: selectedText,
                  highlightAreas: props.highlightAreas,
                  position: props.selectionRegion,
                  chatHistory: [{ role: 'user', content: selectionPayload.displayMessage }],
                  isLoading: true,
                },
              ]);

              setActiveHighlightId(id);
              props.cancel();
              if (onSelection) onSelection(selectionPayload.displayMessage, 'user', true);
              handleInitialAsk(id, selectionPayload.backendPrompt);
              return;

            }}
            className="flex items-center gap-1 rounded-full bg-pixiu p-2 text-white shadow-lg transition-transform hover:scale-110"
          >
            <Sparkles size={18} />
            <span className="pr-1 text-xs font-bold">AI 解释</span>
          </button>
        )}
      </div>
    ),
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
            fileUrl={fileUrl}
            plugins={[defaultLayoutPluginInstance, highlightPluginInstance]}
            theme="light"
            onDocumentLoad={handleDocumentLoad}
            onPageChange={handleViewerPageChange}
          />
        </Worker>
      ) : (
        <div className="flex h-full flex-col items-center justify-center bg-slate-50 text-slate-400">
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
