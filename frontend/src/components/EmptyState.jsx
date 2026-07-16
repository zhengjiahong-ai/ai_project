import React from 'react';
import { Info } from 'lucide-react';

/**
 * Generic empty-state placeholder shown when a panel has no content.
 */
export function EmptyState({
  icon: Icon = Info,
  title = '暂无内容',
  description = '',
  className = '',
}) {
  return (
    <div className={`theme-empty-state flex flex-col items-center justify-center gap-3 p-8 text-center ${className}`}>
      <Icon size={32} className="theme-text-muted" />
      <p className="theme-text-primary text-sm font-semibold">{title}</p>
      {description && (
        <p className="theme-text-muted text-xs max-w-xs">{description}</p>
      )}
    </div>
  );
}
