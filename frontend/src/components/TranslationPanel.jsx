import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Archive, Languages, Loader2, RefreshCw, ScrollText } from 'lucide-react';

import { buildTranslationArtifact } from './artifactModel.ts';
import MarkdownContent from './MarkdownContent';
import { createTranslationPanelViewModel } from './translationPanelModel.js';
import { buildFidelityTranslationLayout } from '../utils/pdfTranslationLayout.js';

const ROLE_CLASS_NAMES = {
  title: 'text-center',
  meta: 'text-center theme-text-secondary',
  heading: 'theme-text-primary',
  body: 'theme-text-secondary',
};

const resolveRoleStyle = (block) => {
  const fontSize = Number(block?.style?.fontSize || 12);
  const fontWeight = block?.style?.fontWeight === 'bold' ? 700 : 400;
  const italic = block?.style?.italic ? 'italic' : 'normal';

  if (block?.role === 'title') {
    return {
      fontSize: `${Math.max(26, Math.min(36, fontSize * 1.22))}px`,
      lineHeight: 1.35,
      fontWeight: Math.max(fontWeight, 700),
      fontStyle: italic,
    };
  }

  if (block?.role === 'meta') {
    return {
      fontSize: `${Math.max(14, Math.min(18, fontSize * 1.05))}px`,
      lineHeight: 1.7,
      fontWeight,
      fontStyle: italic,
    };
  }

  if (block?.role === 'heading') {
    return {
      fontSize: `${Math.max(16, Math.min(22, fontSize * 1.08))}px`,
      lineHeight: 1.65,
      fontWeight: Math.max(fontWeight, 600),
      fontStyle: italic,
    };
  }

  return {
    fontSize: `${Math.max(15, Math.min(18, fontSize * 1.08))}px`,
    lineHeight: 1.85,
    fontWeight,
    fontStyle: italic,
  };
};

const resolvePaperTextStyle = (item, stageWidth, viewportWidth) => {
  const viewportSafeWidth = Math.max(Number(viewportWidth) || 1, 1);
  const sourceFontSize = Number(item?.style?.fontSize || 12);
  const fontSize = Math.max(10, Number(((sourceFontSize * stageWidth) / viewportSafeWidth).toFixed(2)));
  const fontWeight = item?.style?.fontWeight === 'bold' ? 700 : 400;

  return {
    fontSize: `${fontSize}px`,
    lineHeight: fontSize >= 16 ? 1.55 : 1.65,
    fontWeight,
    fontStyle: item?.style?.italic ? 'italic' : 'normal',
    textAlign: item?.style?.textAlign || 'left',
  };
};

const splitPlainTranslationParagraphs = (translatedText) =>
  String(translatedText || '')
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

const splitPlainFallbackContent = (translatedText) => {
  const paragraphs = splitPlainTranslationParagraphs(translatedText);
  const bodyStartIndex = paragraphs.findIndex((paragraph, index) => {
    if (index === 0) {
      return false;
    }

    return paragraph.length > 120 || /^摘要/.test(paragraph);
  });
  const headerCount = bodyStartIndex > 0 ? bodyStartIndex : Math.min(paragraphs.length, 4);

  return {
    headerParagraphs: paragraphs.slice(0, headerCount),
    bodyParagraphs: paragraphs.slice(headerCount),
  };
};

const TranslationStructuredBlock = ({ block }) => (
  <article className={ROLE_CLASS_NAMES[block?.role] || ROLE_CLASS_NAMES.body}>
    <div style={resolveRoleStyle(block)}>
      <MarkdownContent className="translation-overlay-markdown">{block?.translatedText || ''}</MarkdownContent>
    </div>
  </article>
);

const renderStructuredItem = (item) => {
  return <TranslationStructuredBlock key={item.id} block={item} />;
};

const TranslationStructuredStage = ({ readableLayout }) => {
  if (!readableLayout || readableLayout.sections.length === 0) {
    return null;
  }

  return (
    <div className="theme-card-soft rounded-2xl p-4">
      <div className="theme-panel mx-auto max-w-[960px] rounded-[28px] px-6 py-8 shadow-sm sm:px-8 md:px-10">
        <div className="space-y-8">
          {readableLayout.sections.map((section, index) => {
            if (section.type === 'columns') {
              const hasLeft = section.left.length > 0;
              const hasRight = section.right.length > 0;

              if (!hasLeft || !hasRight) {
                const singleColumnItems = hasLeft ? section.left : section.right;
                return (
                  <div key={`section-${index}`} className="space-y-5">
                    {singleColumnItems.map((item) => renderStructuredItem(item))}
                  </div>
                );
              }

              return (
                <div key={`section-${index}`} className="grid gap-8 lg:grid-cols-2">
                  <div className="space-y-5">{section.left.map((item) => renderStructuredItem(item))}</div>
                  <div className="space-y-5">{section.right.map((item) => renderStructuredItem(item))}</div>
                </div>
              );
            }

            return (
              <div key={`section-${index}`} className="space-y-5">
                {section.items.map((item) => renderStructuredItem(item))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

const TranslationPlainColumnFallbackStage = ({ pageLayout, translatedText }) => {
  const { headerParagraphs, bodyParagraphs } = splitPlainFallbackContent(translatedText);
  const viewport = pageLayout?.viewport || {};
  const pageAspectRatio = Math.max(Number(viewport?.height || 800) / Math.max(Number(viewport?.width || 600), 1), 1.1);

  return (
    <div className="theme-card-soft rounded-2xl p-4">
      <div className="theme-panel theme-border mx-auto max-w-[960px] rounded-[28px] border px-8 py-10 shadow-sm sm:px-12">
        <div style={{ minHeight: `${Math.min(1180, Math.max(680, pageAspectRatio * 560))}px` }}>
          {headerParagraphs.length > 0 && (
            <div className="theme-text-primary mx-auto max-w-[760px] space-y-5 text-center">
              {headerParagraphs.map((paragraph, index) => (
                <div
                  key={`plain-header-${index}`}
                  className={index <= 1 ? 'text-xl font-semibold leading-relaxed' : 'text-base leading-8 theme-text-secondary'}
                >
                  <MarkdownContent className="translation-overlay-markdown">{paragraph}</MarkdownContent>
                </div>
              ))}
            </div>
          )}

          {bodyParagraphs.length > 0 && (
            <div
              className="theme-text-secondary mt-10 text-[15px]"
              style={{ columnCount: 2, columnGap: '3.5rem', lineHeight: 1.9 }}
            >
              {bodyParagraphs.map((paragraph, index) => (
                <div key={`plain-body-${index}`} className="mb-5 break-inside-avoid text-justify">
                  <MarkdownContent className="translation-overlay-markdown">{paragraph}</MarkdownContent>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const TranslationFidelityTextBlock = ({ item, stageWidth, viewportWidth, registerRef }) => (
  <article
    ref={registerRef(item.id)}
    className="absolute theme-text-primary"
    style={{
      left: `${item.left * stageWidth}px`,
      top: `${item.top * stageWidth}px`,
      width: `${item.width * stageWidth}px`,
      minHeight: `${item.baseHeight * stageWidth}px`,
    }}
  >
    <div style={resolvePaperTextStyle(item, stageWidth, viewportWidth)}>
      <MarkdownContent className="translation-overlay-markdown">{item?.translatedText || ''}</MarkdownContent>
    </div>
  </article>
);

const TranslationFidelityStage = ({ pageLayout, translatedBlocks, resetKey }) => {
  const stageRef = useRef(null);
  const textRefs = useRef({});
  const [stageWidth, setStageWidth] = useState(0);
  const [measuredHeightUnits, setMeasuredHeightUnits] = useState({});

  const fidelityLayout = useMemo(
    () => buildFidelityTranslationLayout(pageLayout, translatedBlocks, measuredHeightUnits),
    [measuredHeightUnits, pageLayout, translatedBlocks],
  );

  useEffect(() => {
    textRefs.current = {};
    const frameId = window.requestAnimationFrame(() => setMeasuredHeightUnits({}));
    return () => window.cancelAnimationFrame(frameId);
  }, [resetKey]);

  useEffect(() => {
    const node = stageRef.current;
    if (!node) {
      return undefined;
    }

    const updateWidth = (nextWidth) => {
      const normalizedWidth = Math.max(0, Number(nextWidth) || 0);
      setStageWidth((previousWidth) => (Math.abs(previousWidth - normalizedWidth) > 1 ? normalizedWidth : previousWidth));
    };

    updateWidth(node.getBoundingClientRect().width);

    if (typeof ResizeObserver === 'undefined') {
      const handleResize = () => updateWidth(node.getBoundingClientRect().width);
      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    }

    const observer = new ResizeObserver((entries) => {
      const entryWidth = entries[0]?.contentRect?.width ?? node.getBoundingClientRect().width;
      updateWidth(entryWidth);
    });
    observer.observe(node);

    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    if (!stageWidth || !fidelityLayout?.positionedItems?.length) {
      return undefined;
    }

    const frameId = window.requestAnimationFrame(() => {
      const textItems = fidelityLayout.positionedItems.filter((item) => item.kind === 'text');
      if (textItems.length === 0) {
        return;
      }

      const nextMeasuredHeights = {};
      textItems.forEach((item) => {
        const node = textRefs.current[item.id];
        if (!node) {
          return;
        }

        const measuredHeight = node.getBoundingClientRect().height / stageWidth;
        if (!Number.isFinite(measuredHeight) || measuredHeight <= 0) {
          return;
        }

        nextMeasuredHeights[item.id] = Math.max(item.baseHeight, Number(measuredHeight.toFixed(6)));
      });

      if (Object.keys(nextMeasuredHeights).length === 0) {
        return;
      }

      setMeasuredHeightUnits((previousHeights) => {
        let changed = false;
        const mergedHeights = {};

        textItems.forEach((item) => {
          const nextHeight = nextMeasuredHeights[item.id] || previousHeights[item.id] || item.baseHeight;
          mergedHeights[item.id] = nextHeight;
          if (Math.abs((previousHeights[item.id] || 0) - nextHeight) > 0.01) {
            changed = true;
          }
        });

        if (Object.keys(previousHeights).length !== Object.keys(mergedHeights).length) {
          changed = true;
        }

        return changed ? mergedHeights : previousHeights;
      });
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [fidelityLayout, stageWidth]);

  if (!fidelityLayout) {
    return null;
  }

  const registerTextRef = (itemId) => (node) => {
    if (node) {
      textRefs.current[itemId] = node;
      return;
    }

    delete textRefs.current[itemId];
  };
  const stageMaxWidth = fidelityLayout.orientation === 'landscape' ? '1100px' : '960px';

  return (
    <div className="theme-card-soft rounded-2xl p-4">
      <div ref={stageRef} className="mx-auto w-full" style={{ maxWidth: stageMaxWidth }}>
        <div
          className="theme-panel theme-border relative overflow-hidden rounded-[28px] border shadow-sm"
          data-orientation={fidelityLayout.orientation}
          data-column-mode={fidelityLayout.columnMode}
          style={{
            minHeight: '240px',
            height: stageWidth ? `${Math.max(240, fidelityLayout.pageHeight * stageWidth)}px` : undefined,
          }}
        >
          {stageWidth > 0 &&
            fidelityLayout.positionedItems.map((item) =>
              <TranslationFidelityTextBlock
                key={item.id}
                item={item}
                stageWidth={stageWidth}
                viewportWidth={fidelityLayout.viewport.width}
                registerRef={registerTextRef}
              />,
            )}
        </div>
      </div>
    </div>
  );
};

const TranslationPanel = ({ pdfId, pdfFileName, currentPage = 0, pageData = null, onRetry, onCaptureArtifact }) => {
  const pageNumber = Number.isFinite(currentPage) ? currentPage + 1 : 1;
  const status = pageData?.status || 'idle';
  const translatedText = pageData?.translatedText || '';
  const errorMessage = pageData?.error || '';
  const fidelityResetKey = `${currentPage}:${pageData?.updatedAt || 0}:${pageData?.translatedBlocks?.length || 0}`;
  const viewModel = useMemo(() => createTranslationPanelViewModel(pageData), [pageData]);
  const {
    readableLayout,
    canRenderFidelity,
    canRenderStructuredFallback,
    canRenderPlainColumnFallback,
    shouldShowPlainTranslation,
  } = viewModel;
  const translationArtifact = useMemo(
    () => buildTranslationArtifact({ pdfId, pdfFileName, pageIndex: currentPage, translatedText }),
    [currentPage, pdfFileName, pdfId, translatedText],
  );

  return (
    <div className="theme-panel-muted flex h-full flex-col">
      <div className="theme-panel theme-border sticky top-0 z-10 flex items-center justify-between border-b px-6 py-4">
        <div>
          <h2 className="theme-text-primary flex items-center gap-2 text-lg font-bold">
            <Languages size={20} className="text-pixiu" />
            全景翻译
          </h2>
          <p className="theme-text-secondary mt-1 text-xs">{pdfFileName ? `${pdfFileName} · 第 ${pageNumber} 页` : `第 ${pageNumber} 页`}</p>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => translationArtifact && onCaptureArtifact?.(translationArtifact)}
            disabled={status !== 'success' || !translationArtifact || !onCaptureArtifact}
            title={!pdfId ? '请先打开一篇论文。' : !translationArtifact ? '当前页译文尚未生成。' : '保存当前页译文'}
            className="theme-button-secondary flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Archive size={14} />
            加入工作台
          </button>
          <button
            type="button"
            onClick={onRetry}
            disabled={status === 'loading'}
            className="theme-button-secondary flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw size={14} />
            重试翻译
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto p-6">
        {status === 'loading' && (
          <div className="theme-card flex items-center gap-3 rounded-2xl p-5">
            <Loader2 size={18} className="animate-spin text-pixiu" />
            <div>
              <p className="theme-text-primary text-sm font-semibold">正在生成当前页译文...</p>
            </div>
          </div>
        )}

        {status === 'error' && (
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-500 shadow-sm">
            <p className="font-semibold">当前页翻译失败</p>
            <p className="mt-2 leading-relaxed">{errorMessage || '生成译文时出现异常，请稍后重试。'}</p>
          </div>
        )}

        {status === 'empty' && (
          <div className="rounded-2xl border border-amber-400/20 bg-amber-500/10 p-5 text-sm text-amber-500 shadow-sm">
            <p className="font-semibold">当前页没有可翻译的正文内容</p>
            <p className="mt-2 leading-relaxed">{errorMessage || '这一页可能主要由图片、表格或扫描内容组成，因此没有提取到可翻译正文。'}</p>
          </div>
        )}

        {status === 'idle' && (
          <div className="theme-card flex min-h-[220px] flex-col items-center justify-center rounded-2xl border-dashed p-8 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-pixiu/10">
              <ScrollText size={24} className="text-pixiu" />
            </div>
            <p className="theme-text-primary text-sm font-semibold">打开全景翻译后，这里会展示当前页的译文。</p>
            <p className="theme-text-secondary mt-2 max-w-xs text-xs leading-relaxed">
              新版会尽量保持原论文的标题区与双栏结构；图片、图表和表格区域不会显示在译文中。
            </p>
          </div>
        )}

        {canRenderFidelity && (
          <TranslationFidelityStage
            pageLayout={pageData?.pageLayout}
            translatedBlocks={pageData?.translatedBlocks}
            resetKey={fidelityResetKey}
          />
        )}

        {canRenderStructuredFallback && <TranslationStructuredStage readableLayout={readableLayout} />}

        {canRenderPlainColumnFallback && (
          <TranslationPlainColumnFallbackStage pageLayout={pageData?.pageLayout} translatedText={translatedText} />
        )}

        {shouldShowPlainTranslation && (
          <div className="theme-card rounded-2xl p-5">
            <div className="theme-text-muted mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
              <Languages size={14} className="text-pixiu" />
              译文结果
            </div>
            <div className="theme-text-secondary whitespace-pre-wrap text-[15px] leading-8">{translatedText}</div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TranslationPanel;
