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
import { buildPageLayout, normalizeExcludedZones } from '../utils/pdfTranslationLayout.js';
import MarkdownContent from './MarkdownContent';
import { getMessageMarkdownClassName } from './MessageMarkdownRenderer';

const workerUrl = 'https://unpkg.com/pdfjs-dist@3.4.120/build/pdf.worker.min.js';

const buildPageSnapshot = async (page, maxRenderWidth = 1200) => {
  const baseViewport = page.getViewport({ scale: 1 });
  const safeWidth = Math.max(baseViewport.width || 1, 1);
  const scale = Math.min(2, Math.max(1, maxRenderWidth / safeWidth));
  const renderViewport = page.getViewport({ scale });
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d', { alpha: false });

  canvas.width = Math.ceil(renderViewport.width);
  canvas.height = Math.ceil(renderViewport.height);

  if (!context) {
    throw new Error('Canvas 2D context is unavailable.');
  }

  await page.render({ canvasContext: context, viewport: renderViewport }).promise;
  return canvas.toDataURL('image/png');
};

const loadImage = (src) =>
  new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = src;
  });

const buildFigureSnippets = async (backgroundImage, excludedZones = []) => {
  const normalizedZones = normalizeExcludedZones(excludedZones);
  if (!backgroundImage || normalizedZones.length === 0) {
    return [];
  }

  const image = await loadImage(backgroundImage);

  return normalizedZones.reduce((snippets, zone, index) => {
    const left = Math.max(0, Math.floor(zone.bbox.left * image.width));
    const top = Math.max(0, Math.floor(zone.bbox.top * image.height));
    const width = Math.max(1, Math.ceil(zone.bbox.width * image.width));
    const height = Math.max(1, Math.ceil(zone.bbox.height * image.height));
    const paddingX = Math.max(6, Math.round(width * 0.015));
    const paddingY = Math.max(6, Math.round(height * 0.02));
    const sourceX = Math.max(0, left - paddingX);
    const sourceY = Math.max(0, top - paddingY);
    const sourceWidth = Math.min(image.width - sourceX, width + paddingX * 2);
    const sourceHeight = Math.min(image.height - sourceY, height + paddingY * 2);

    if (sourceWidth <= 0 || sourceHeight <= 0) {
      return snippets;
    }

    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (!context) {
      return snippets;
    }

    canvas.width = sourceWidth;
    canvas.height = sourceHeight;
    context.drawImage(image, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, sourceWidth, sourceHeight);

    snippets.push({
      id: `figure-${index + 1}`,
      type: zone.type || 'figure',
      bbox: zone.bbox,
      image: canvas.toDataURL('image/png'),
    });

    return snippets;
  }, []);
};

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
        <span className="flex items-center gap-1.5 text-xs font-bold text-pixiu">
          <Sparkles size={14} /> AI 翻译
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
  initialHighlights,
  onHighlightsChange,
  onPageChange,
  onPageTextExtracted,
  theme = 'light',
  translationLayoutIndex = {},
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
        const viewport = page.getViewport({ scale: 1 });
        const { pageText, pageLayout } = buildPageLayout(textContent, viewport);
        const excludedZones = translationLayoutIndex?.[pageIndex]?.excludedZones || [];
        let backgroundImage = '';
        let figureSnippets = [];

        try {
          backgroundImage = await buildPageSnapshot(page);
          figureSnippets = await buildFigureSnippets(backgroundImage, excludedZones);
        } catch (snapshotError) {
          console.warn(`Failed to render page snapshot for page ${pageIndex + 1}.`, snapshotError);
        }

        if (requestedPdfId !== latestPdfIdRef.current) {
          return;
        }
        onPageTextExtracted({
          pageIndex,
          pageText,
          pageLayout,
          backgroundImage,
          figureSnippets,
        });
      } catch (error) {
        console.warn(`Failed to extract text for page ${pageIndex + 1}.`, error);
        if (requestedPdfId !== latestPdfIdRef.current) {
          return;
        }
        onPageTextExtracted({
          pageIndex,
          pageText: '',
          pageLayout: null,
          backgroundImage: '',
          figureSnippets: [],
        });
      }
    },
    [onPageTextExtracted, translationLayoutIndex],
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
      const aiResponse = response?.data?.reply ?? response?.reply ?? response?.message ?? '鏆傛棤鍥炲';

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
            <span className="pr-1 text-xs font-bold">AI 翻译</span>
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

