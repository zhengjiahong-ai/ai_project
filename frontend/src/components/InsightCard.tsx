import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

import MarkdownContent from './MarkdownContent.jsx';
import { buildInsightCardModel, type InsightCardModelOutput } from './insightCardModel';

interface InsightCardProps {
  title?: string;
  icon?: React.ReactNode;
  content?: string;
  summary?: string;
  keyPoints?: string[];
  meta?: React.ReactNode;
  footer?: React.ReactNode;
  maxPoints?: number;
  detailsTitle?: string;
  defaultExpanded?: boolean;
  className?: string;
}


const InsightCard: React.FC<InsightCardProps> = ({
  title = '',
  icon = null,
  content = '',
  summary = '',
  keyPoints = [],
  meta = null,
  footer = null,
  maxPoints = 4,
  detailsTitle = '查看详情',
  defaultExpanded = false,
  className = '',
}) => {
  const model: InsightCardModelOutput = buildInsightCardModel({
    content,
    summary,
    keyPoints,
    maxPoints,
    detailsTitle,
    defaultExpanded,
  }) as InsightCardModelOutput;

  const [isExpanded, setIsExpanded] = React.useState<boolean>(model.defaultExpanded);
  const shouldShowCompactContent: boolean = !(model.hasDetails && isExpanded);

  return (
    <section className={`theme-card rounded-2xl p-4 ${className}`.trim()}>
      {(title || meta || icon) && (
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && (
              <div className="theme-text-primary flex items-center gap-2 text-sm font-semibold">
                {icon}
                <span className="min-w-0 truncate">{title}</span>
              </div>
            )}
          </div>
          {meta && <div className="shrink-0">{meta}</div>}
        </div>
      )}

      {shouldShowCompactContent && (
        <div className="theme-text-primary text-sm leading-7">{model.summary}</div>
      )}

      {shouldShowCompactContent && model.hasPoints && (
        <div className="mt-3 space-y-2">
          {model.points.map((point: string) => (
            <div key={point} className="theme-card-soft rounded-xl px-3 py-2 text-sm leading-6 theme-text-secondary">
              {point}
            </div>
          ))}
        </div>
      )}

      {model.hasDetails && (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => setIsExpanded((current: boolean) => !current)}
            className="theme-button-secondary inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
          >
            {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {isExpanded ? '收起详情' : model.detailsTitle}
          </button>

          {isExpanded && (
            <div className="theme-markdown-panel mt-3 rounded-xl p-4 text-sm leading-7">
              <MarkdownContent>{model.details}</MarkdownContent>
            </div>
          )}
        </div>
      )}

      {footer && <div className="mt-4">{footer}</div>}
    </section>
  );
};

export default InsightCard;
