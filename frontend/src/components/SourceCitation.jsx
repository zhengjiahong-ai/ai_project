import React, { useState } from 'react';
import { ChevronDown, ChevronUp, FileText, Link2 } from 'lucide-react';

import { normalizeEvidenceSources } from './evidenceCitationModel.js';

export const SourceChip = ({ source, onJumpToSource, onShowDetails }) => {
  const handleClick = async () => {
    if (!source?.canJumpToSource || !onJumpToSource) {
      onShowDetails?.(source);
      return;
    }

    try {
      const didJump = await onJumpToSource(source);
      if (didJump === false) {
        onShowDetails?.(source);
      }
    } catch {
      onShowDetails?.(source);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className="source-link-chip inline-flex items-center gap-1"
      title={source?.canJumpToSource ? '跳回原文' : '查看来源片段'}
    >
      {source?.canJumpToSource ? <Link2 size={12} /> : <FileText size={12} />}
      <span>
        {source?.canJumpToSource ? `跳回原文 ${source.locationLabel}` : `查看来源 ${source?.sourceId || ''}`}
      </span>
    </button>
  );
};

export const SourceList = ({ sources, onJumpToSource, emptyText = '', variant = 'default' }) => {
  const [expandedSourceIds, setExpandedSourceIds] = useState([]);
  const normalizedSources = normalizeEvidenceSources(sources);

  if (normalizedSources.length === 0) {
    return emptyText ? <div className="theme-text-muted text-xs">{emptyText}</div> : null;
  }

  const toggleDetails = (source) => {
    setExpandedSourceIds((current) => (
      current.includes(source.sourceId)
        ? current.filter((sourceId) => sourceId !== source.sourceId)
        : [...current, source.sourceId]
    ));
  };

  return (
    <div className={`source-list space-y-2 ${variant === 'agent' ? 'agent-body' : ''}`}>
      {normalizedSources.map((source) => {
        const isExpanded = expandedSourceIds.includes(source.sourceId);
        return (
          <div key={source.sourceId} className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <SourceChip source={source} onJumpToSource={onJumpToSource} onShowDetails={toggleDetails} />
              {source.canJumpToSource && source.text && (
                <button
                  type="button"
                  onClick={() => toggleDetails(source)}
                  className="theme-text-muted inline-flex items-center gap-1 text-[10px] font-semibold"
                >
                  {isExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                  {isExpanded ? '收起片段' : '查看片段'}
                </button>
              )}
            </div>
            {isExpanded && (
              <div className={`mt-2 rounded-xl border px-3 py-2 text-[11px] leading-6 ${variant === 'agent' ? 'agent-card-soft' : 'theme-card-soft theme-border'}`}>
                <div className="mb-1 flex flex-wrap gap-x-3 gap-y-1 text-[10px] font-semibold opacity-75">
                  <span>{source.sourceId}</span>
                  {source.sourceType !== 'unknown' && <span>{source.sourceType}</span>}
                  {source.sectionId && <span>{source.sectionId}</span>}
                  {Number.isInteger(source.chunkIndex) && <span>chunk {source.chunkIndex}</span>}
                </div>
                <div className="whitespace-pre-wrap">{source.text || '该旧来源没有缓存正文片段。'}</div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default SourceList;
