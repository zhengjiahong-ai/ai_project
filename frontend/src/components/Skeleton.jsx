import React from 'react';

/**
 * Generic skeleton placeholder with pulse animation.
 */
export function Skeleton({ className = '', ...props }) {
  return (
    <div
      className={`animate-pulse rounded bg-slate-200 dark:bg-slate-700 ${className}`}
      aria-hidden="true"
      {...props}
    />
  );
}

/**
 * Single-line skeleton (e.g. for text paragraphs).
 */
export function SkeletonLine({ className = '', ...props }) {
  return (
    <Skeleton className={`h-4 w-full ${className}`} {...props} />
  );
}

/**
 * Card-shaped skeleton with header + body lines.
 */
export function SkeletonCard({ className = '', ...props }) {
  return (
    <div className={`theme-card space-y-3 rounded-lg border p-4 ${className}`} aria-hidden="true" {...props}>
      <Skeleton className="h-5 w-1/3" />
      <SkeletonLine />
      <SkeletonLine className="w-4/5" />
      <SkeletonLine className="w-2/3" />
    </div>
  );
}
