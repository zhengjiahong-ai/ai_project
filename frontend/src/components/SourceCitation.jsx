import React, { useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink, FileText, Globe, Link2 } from 'lucide-react';

import { normalizeEvidenceSources } from './evidenceCitationModel.js';

const formatExternalRetrieved = (value) => {
  if (!value) return '';
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('zh-CN', { hour12: false });
  } catch {
    return value;
  }
};

const ExternalSourceExpanded = ({ source }) => (
  <div className="space-y-2 text-[11px] leading-6">
    <div className="mb-1 flex flex-wrap gap-x-3 gap-y-1 text-[10px] font-semibold opacity-75">
      <span className="inline-flex items-center gap-1 rounded-full border border-indigo-400/25 bg-indigo-500/10 px-2 py-0.5 text-indigo-400">
        external_academic
      </span>
      {source.provider && <span>{source.provider}</span>}
      {source.providerId && <span className="opacity-60">{source.providerId}</span>}
    </div>
    {source.title && (
      <div>
        <span className="font-semibold">Title: </span>
        {source.title}
      </div>
    )}
    {source.authors && source.authors.length > 0 && (
      <div>
        <span className="font-semibold">Authors: </span>
        {source.authors.join(', ')}
      </div>
    )}
    {Number.isInteger(source.year) && (
      <div>
        <span className="font-semibold">Year: </span>
        {source.year}
      </div>
    )}
    {source.doi && (
      <div>
        <span className="font-semibold">DOI: </span>
        {source.doi}
      </div>
    )}
    {source.url && (
      <div>
        <span className="font-semibold">URL: </span>
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-indigo-400 underline underline-offset-2"
        >
          {source.url}
        </a>
      </div>
    )}
    {source.retrievedAt && (
      <div>
        <span className="font-semibold">Retrieved: </span>
        {formatExternalRetrieved(source.retrievedAt)}
      </div>
    )}
    {source.license && (
      <div>
        <span className="font-semibold">License: </span>
        {source.license}
      </div>
    )}
    {source.abstract && (
      <div>
        <span className="font-semibold">Abstract: </span>
        <span className="opacity-75">{source.abstract}</span>
      </div>
    )}
    {source.text && (
      <div className="mt-2 border-t border-[color:var(--border)] pt-2">
        <span className="font-semibold">Evidence: </span>
        <span className="opacity-75 whitespace-pre-wrap">{source.text}</span>
      </div>
    )}
  </div>
);

export const SourceChip = ({ source, onJumpToSource, onShowDetails }) => {
  const isExternal = source?.isExternal;

  const handleClick = async () => {
    if (!source?.canJumpToSource || !onJumpToSource) {
      onShowDetails?.(source);
      return;
    }

    if (isExternal) {
      if (source.externalUrl) {
        window.open(source.externalUrl, '_blank', 'noopener');
      }
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

  if (isExternal) {
    return (
      <button
        type="button"
        onClick={handleClick}
        className="source-external-chip inline-flex items-center gap-1 rounded-full border border-indigo-400/25 bg-indigo-500/10 px-2.5 py-1 text-[11px] font-semibold text-indigo-400 transition hover:opacity-80"
        title={source?.canJumpToSource ? '打开外部来源' : '查看外部来源元数据'}
      >
        {source?.canJumpToSource ? <Globe size={12} /> : <FileText size={12} />}
        <span>
          外部来源 · {source.locationLabel || source.provider || 'external'}
        </span>
        {source?.canJumpToSource && <ExternalLink size={10} className="opacity-60" />}
      </button>
    );
  }

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
        const isExternal = source?.isExternal;
        return (
          <div key={source.sourceId} className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <SourceChip source={source} onJumpToSource={onJumpToSource} onShowDetails={toggleDetails} />
              {((source.canJumpToSource && source.text) || isExternal) && (
                <button
                  type="button"
                  onClick={() => toggleDetails(source)}
                  className="theme-text-muted inline-flex items-center gap-1 text-[10px] font-semibold"
                >
                  {isExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                  {isExpanded ? (isExternal ? '收起详情' : '收起片段') : (isExternal ? '查看详情' : '查看片段')}
                </button>
              )}
            </div>
            {isExpanded && (
              <div className={`mt-2 rounded-xl border px-3 py-2 text-[11px] leading-6 ${variant === 'agent' ? 'agent-card-soft' : 'theme-card-soft theme-border'}`}>
                {isExternal ? (
                  <ExternalSourceExpanded source={source} />
                ) : (
                  <>
                    <div className="mb-1 flex flex-wrap gap-x-3 gap-y-1 text-[10px] font-semibold opacity-75">
                      <span>{source.sourceId}</span>
                      {source.sourceType !== 'unknown' && <span>{source.sourceType}</span>}
                      {source.sectionId && <span>{source.sectionId}</span>}
                      {Number.isInteger(source.chunkIndex) && <span>chunk {source.chunkIndex}</span>}
                    </div>
                    <div className="whitespace-pre-wrap">{source.text || '该旧来源没有缓存正文片段。'}</div>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default SourceList;
