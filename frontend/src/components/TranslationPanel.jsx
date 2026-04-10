import React, { useMemo } from 'react';
import { Image, Languages, Loader2, RefreshCw, ScrollText } from 'lucide-react';

import MarkdownContent from './MarkdownContent';
import { buildReadableTranslationLayout } from '../utils/pdfTranslationLayout.js';
import { canRenderOverlay } from '../utils/translationState.js';

const ROLE_CLASS_NAMES = {
  title: 'text-center',
  meta: 'text-center text-slate-600',
  heading: 'text-slate-800',
  body: 'text-slate-700',
};

const FIGURE_TYPE_LABELS = {
  figure: '图片 / 图表',
  table: '表格',
  formula: '公式区域',
  head: '标题区域',
  excluded: '保留区域',
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

const resolveFigureAlignment = (figure) => {
  const bbox = figure?.bbox || {};
  const center = bbox.left + bbox.width / 2;

  if (center < 0.36) {
    return 'mr-auto';
  }

  if (center > 0.64) {
    return 'ml-auto';
  }

  return 'mx-auto';
};

const resolveFigureWidth = (figure, isColumn) => {
  if (isColumn) {
    return '100%';
  }

  const bboxWidth = Number(figure?.bbox?.width || 0.8);
  const percentage = Math.max(42, Math.min(96, bboxWidth * 100 + 6));
  return `${percentage}%`;
};

const TranslationStructuredBlock = ({ block }) => (
  <article className={ROLE_CLASS_NAMES[block?.role] || ROLE_CLASS_NAMES.body}>
    <div style={resolveRoleStyle(block)}>
      <MarkdownContent className="translation-page-markdown">{block?.translatedText || ''}</MarkdownContent>
    </div>
  </article>
);

const TranslationFigureSnippet = ({ figure, isColumn = false }) => {
  const label = FIGURE_TYPE_LABELS[figure?.type] || FIGURE_TYPE_LABELS.figure;

  return (
    <figure
      className={`overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 shadow-sm ${resolveFigureAlignment(
        figure,
      )}`}
      style={{ width: resolveFigureWidth(figure, isColumn) }}
    >
      <div className="flex items-center gap-2 border-b border-slate-200 bg-white/80 px-4 py-2 text-xs font-semibold text-slate-500">
        <Image size={14} className="text-pixiu" />
        <span>{label}</span>
      </div>
      <div className="bg-slate-100 p-3">
        <img
          src={figure?.image}
          alt={label}
          className="w-full rounded-xl bg-white object-contain"
          loading="lazy"
        />
      </div>
    </figure>
  );
};

const renderStructuredItem = (item, isColumn = false) => {
  if (item?.kind === 'figure') {
    return <TranslationFigureSnippet key={item.id} figure={item} isColumn={isColumn} />;
  }

  return <TranslationStructuredBlock key={item.id} block={item} />;
};

const TranslationStructuredStage = ({ readableLayout }) => {
  if (!readableLayout || readableLayout.sections.length === 0) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-100 p-4 shadow-sm">
      <div className="mx-auto max-w-[960px] rounded-[28px] bg-white px-6 py-8 shadow-sm sm:px-8 md:px-10">
        <div className="space-y-8">
          {readableLayout.sections.map((section, index) => {
            if (section.type === 'columns') {
              const hasLeft = section.left.length > 0;
              const hasRight = section.right.length > 0;

              if (!hasLeft || !hasRight) {
                const singleColumnItems = hasLeft ? section.left : section.right;
                return (
                  <div key={`section-${index}`} className="space-y-5">
                    {singleColumnItems.map((item) => renderStructuredItem(item, true))}
                  </div>
                );
              }

              return (
                <div key={`section-${index}`} className="grid gap-8 lg:grid-cols-2">
                  <div className="space-y-5">{section.left.map((item) => renderStructuredItem(item, true))}</div>
                  <div className="space-y-5">{section.right.map((item) => renderStructuredItem(item, true))}</div>
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

const TranslationPanel = ({ pdfFileName, currentPage = 0, pageData = null, onRetry }) => {
  const pageNumber = Number.isFinite(currentPage) ? currentPage + 1 : 1;
  const status = pageData?.status || 'idle';
  const translatedText = pageData?.translatedText || '';
  const errorMessage = pageData?.error || '';
  const readableLayout = useMemo(
    () => buildReadableTranslationLayout(pageData?.pageLayout, pageData?.translatedBlocks, pageData?.figureSnippets),
    [pageData?.pageLayout, pageData?.translatedBlocks, pageData?.figureSnippets],
  );
  const canRenderStructured =
    Boolean(readableLayout?.sections?.length) &&
    (pageData?.renderMode === 'overlay' || canRenderOverlay(pageData));

  return (
    <div className="flex h-full flex-col bg-slate-50/40">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-white px-6 py-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-slate-800">
            <Languages size={20} className="text-pixiu" />
            全景翻译
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            {pdfFileName ? `${pdfFileName} · 第 ${pageNumber} 页` : `第 ${pageNumber} 页`}
          </p>
        </div>

        <button
          onClick={onRetry}
          className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:border-pixiu hover:text-pixiu"
        >
          <RefreshCw size={14} />
          重试当前页
        </button>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto p-6">
        {status === 'loading' && (
          <div className="flex items-center gap-3 rounded-2xl border border-pixiu/10 bg-white p-5 shadow-sm">
            <Loader2 size={18} className="animate-spin text-pixiu" />
            <div>
              <p className="text-sm font-semibold text-slate-700">正在生成当前页译文...</p>
              <p className="text-xs text-slate-500">会优先保留图表和结构化排版，失败时自动降级为连续译文。</p>
            </div>
          </div>
        )}

        {status === 'error' && (
          <div className="rounded-2xl border border-red-100 bg-red-50 p-5 text-sm text-red-600 shadow-sm">
            <p className="font-semibold">当前页翻译失败</p>
            <p className="mt-2 leading-relaxed">{errorMessage || '请稍后重试，或切换页面后再返回。'}</p>
          </div>
        )}

        {status === 'empty' && !canRenderStructured && (
          <div className="rounded-2xl border border-amber-100 bg-amber-50 p-5 text-sm text-amber-700 shadow-sm">
            <p className="font-semibold">当前页没有可翻译的正文内容</p>
            <p className="mt-2 leading-relaxed">
              {errorMessage || '这一页可能主要由图片、图表或空白区域组成，所以没有生成译文。'}
            </p>
          </div>
        )}

        {status === 'idle' && (
          <div className="flex min-h-[220px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white p-8 text-center shadow-sm">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-pixiu/10">
              <ScrollText size={24} className="text-pixiu" />
            </div>
            <p className="text-sm font-semibold text-slate-700">打开全景翻译后，这里会显示当前页的译文。</p>
            <p className="mt-2 max-w-xs text-xs leading-relaxed text-slate-500">
              如果本页包含图片或图表，右侧会在保留原图的同时显示中文正文。
            </p>
          </div>
        )}

        {canRenderStructured && <TranslationStructuredStage readableLayout={readableLayout} />}

        {translatedText && !canRenderStructured && (
          <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <Languages size={14} className="text-pixiu" />
              中文译文
            </div>
            <div className="whitespace-pre-wrap text-[15px] leading-8 text-slate-700">{translatedText}</div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TranslationPanel;
