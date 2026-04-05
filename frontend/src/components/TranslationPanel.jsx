import React from 'react';
import { Languages, Loader2, RefreshCw, ScrollText } from 'lucide-react';

const TranslationPanel = ({ pdfFileName, currentPage = 0, pageData = null, onRetry }) => {
  const pageNumber = Number.isFinite(currentPage) ? currentPage + 1 : 1;
  const status = pageData?.status || 'idle';
  const sourcePreview = pageData?.sourceText || '';
  const translatedText = pageData?.translatedText || '';
  const errorMessage = pageData?.error || '';

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
              <p className="text-sm font-semibold text-slate-700">正在翻译当前页...</p>
              <p className="text-xs text-slate-500">通常会在几十秒内返回；如果超过 90 秒，系统会自动报错并允许重试。</p>
            </div>
          </div>
        )}

        {status === 'error' && (
          <div className="rounded-2xl border border-red-100 bg-red-50 p-5 text-sm text-red-600 shadow-sm">
            <p className="font-semibold">当前页翻译失败</p>
            <p className="mt-2 leading-relaxed">{errorMessage || '请稍后重试。'}</p>
          </div>
        )}

        {status === 'empty' && (
          <div className="rounded-2xl border border-amber-100 bg-amber-50 p-5 text-sm text-amber-700 shadow-sm">
            <p className="font-semibold">当前页未提取到可翻译文本</p>
            <p className="mt-2 leading-relaxed">
              {errorMessage || '这可能是扫描页、图片页，或该页缺少可提取文字层。'}
            </p>
          </div>
        )}

        {status === 'idle' && (
          <div className="flex min-h-[220px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white p-8 text-center shadow-sm">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-pixiu/10">
              <ScrollText size={24} className="text-pixiu" />
            </div>
            <p className="text-sm font-semibold text-slate-700">等待当前页文本就绪</p>
            <p className="mt-2 max-w-xs text-xs leading-relaxed text-slate-500">
              翻到任意 PDF 页面后，系统会自动提取该页文本并在这里显示逐页中文译文。
            </p>
          </div>
        )}

        {translatedText && (
          <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <Languages size={14} className="text-pixiu" />
              中文译文
            </div>
            <div className="whitespace-pre-wrap text-sm leading-7 text-slate-700">{translatedText}</div>
          </div>
        )}

        {sourcePreview && (
          <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <ScrollText size={14} className="text-slate-500" />
              当前页原文预览
            </div>
            <div className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-xs leading-6 text-slate-500">
              {sourcePreview}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TranslationPanel;
