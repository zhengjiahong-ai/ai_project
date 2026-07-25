import React from 'react';

/**
 * PDF page skeleton placeholder with pulse animation.
 * Mimics a PDF page layout to indicate loading state.
 */
const PdfSkeleton: React.FC = () => (
  <div
    className="pdf-skeleton flex h-full w-full items-center justify-center"
    aria-hidden="true"
    aria-label="PDF 加载中"
  >
    <div className="pdf-skeleton-page theme-panel theme-border w-full max-w-2xl animate-pulse rounded-lg border p-8 shadow-sm">
      {/* Title placeholder */}
      <div className="mb-8 h-6 w-3/5 rounded bg-slate-200 dark:bg-slate-700" />

      {/* Abstract header */}
      <div className="mb-3 h-4 w-1/4 rounded bg-slate-200 dark:bg-slate-700" />

      {/* Paragraph lines */}
      <div className="mb-2 h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
      <div className="mb-2 h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
      <div className="mb-2 h-3 w-11/12 rounded bg-slate-100 dark:bg-slate-800" />
      <div className="mb-2 h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
      <div className="mb-6 h-3 w-4/5 rounded bg-slate-100 dark:bg-slate-800" />

      {/* Section header */}
      <div className="mb-3 h-4 w-1/3 rounded bg-slate-200 dark:bg-slate-700" />

      {/* More paragraph lines */}
      <div className="mb-2 h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
      <div className="mb-2 h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
      <div className="mb-2 h-3 w-10/12 rounded bg-slate-100 dark:bg-slate-800" />
      <div className="mb-2 h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
      <div className="mb-6 h-3 w-3/5 rounded bg-slate-100 dark:bg-slate-800" />

      {/* Section header */}
      <div className="mb-3 h-4 w-2/5 rounded bg-slate-200 dark:bg-slate-700" />

      {/* More paragraph lines */}
      <div className="mb-2 h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
      <div className="mb-2 h-3 w-9/12 rounded bg-slate-100 dark:bg-slate-800" />
      <div className="mb-2 h-3 w-full rounded bg-slate-100 dark:bg-slate-800" />
      <div className="h-3 w-7/12 rounded bg-slate-100 dark:bg-slate-800" />
    </div>
  </div>
);

export default PdfSkeleton;
