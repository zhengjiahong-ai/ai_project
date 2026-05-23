import React, { useDeferredValue, useMemo, useState } from 'react';
import {
  ArrowDownToLine,
  Bookmark,
  Check,
  ChevronDown,
  ChevronUp,
  Edit3,
  Pin,
  Search,
  StickyNote,
  Trash2,
  X,
} from 'lucide-react';

const KIND_LABELS = {
  insight: '洞察卡',
  'chat-answer': '问答卡',
  'critical-summary': '批判总览',
  'critical-claimed': '作者主张',
  'critical-inferred': '真实贡献',
  'critical-critical': '批判结论',
  evidence: '证据卡',
  'background-overview': '背景总览',
  'background-evidence': '背景依据',
  'research-snapshot': '研究快照',
  'research-finding': '研究发现',
  'margin-note': '边注卡',
};

const LANE_LABELS = {
  inbox: '待整理',
  evidence: '证据池',
  argument: '论点区',
  draft: '写作草稿',
};

const normalizeText = (value) => `${value ?? ''}`.trim();

const BottomWorkbench = ({
  cards = [],
  notes = [],
  pdfFileName = '',
  isCollapsed = false,
  onToggleCollapsed,
  onJumpToArtifactSource,
  onJumpToNoteSource,
  onRemoveArtifact,
  onToggleArtifactPinned,
  onUpdateArtifact,
  onCaptureNote,
  onSaveArtifactAsNote,
  onDeleteNote,
}) => {
  const [query, setQuery] = useState('');
  const [activeKind, setActiveKind] = useState('all');
  const [editingArtifactId, setEditingArtifactId] = useState(null);
  const [draftArtifact, setDraftArtifact] = useState({
    title: '',
    summary: '',
    lane: 'inbox',
    tagsText: '',
    userNote: '',
  });
  const deferredQuery = useDeferredValue(query);

  const kindOptions = useMemo(() => {
    const counts = cards.reduce((map, card) => {
      const nextMap = { ...map };
      nextMap[card.kind] = (nextMap[card.kind] || 0) + 1;
      return nextMap;
    }, {});

    return Object.entries(counts).map(([kind, count]) => ({
      kind,
      label: KIND_LABELS[kind] || kind,
      count,
    }));
  }, [cards]);

  const filteredCards = useMemo(() => {
    const normalizedQuery = normalizeText(deferredQuery).toLowerCase();

    return cards.filter((card) => {
      if (activeKind !== 'all' && card.kind !== activeKind) {
        return false;
      }

      if (!normalizedQuery) {
        return true;
      }

      const haystack = [
        card.title,
        card.summary,
        card.content,
        card.kind,
        ...(Array.isArray(card.tags) ? card.tags : []),
      ]
        .join(' ')
        .toLowerCase();

      return haystack.includes(normalizedQuery);
    });
  }, [activeKind, cards, deferredQuery]);

  const filteredNotes = useMemo(() => {
    const normalizedQuery = normalizeText(deferredQuery).toLowerCase();
    if (!normalizedQuery) {
      return notes;
    }

    return notes.filter((note) =>
      [note.text, note.aiInterpretation, note.sourceActionLabel]
        .join(' ')
        .toLowerCase()
        .includes(normalizedQuery),
    );
  }, [deferredQuery, notes]);

  const groupedCards = useMemo(() => {
    const groups = Object.keys(LANE_LABELS).reduce((map, laneKey) => {
      const nextMap = { ...map };
      nextMap[laneKey] = [];
      return nextMap;
    }, {});

    filteredCards.forEach((artifact) => {
      const laneKey = artifact.lane && groups[artifact.lane] ? artifact.lane : 'inbox';
      groups[laneKey].push(artifact);
    });

    return groups;
  }, [filteredCards]);

  const startEditingArtifact = (artifact) => {
    setEditingArtifactId(artifact.artifactId);
    setDraftArtifact({
      title: artifact.title || '',
      summary: artifact.summary || '',
      lane: artifact.lane || 'inbox',
      tagsText: Array.isArray(artifact.tags) ? artifact.tags.join(', ') : '',
      userNote: artifact.userNote || '',
    });
  };

  const cancelEditingArtifact = () => {
    setEditingArtifactId(null);
    setDraftArtifact({
      title: '',
      summary: '',
      lane: 'inbox',
      tagsText: '',
      userNote: '',
    });
  };

  const saveEditingArtifact = (artifactId) => {
    onUpdateArtifact?.(artifactId, {
      title: draftArtifact.title,
      summary: draftArtifact.summary,
      lane: draftArtifact.lane,
      userNote: draftArtifact.userNote,
      tags: draftArtifact.tagsText
        .split(',')
        .map((tag) => normalizeText(tag))
        .filter(Boolean),
    });
    cancelEditingArtifact();
  };

  return (
    <div className="bottom-workbench theme-panel theme-border flex h-full flex-col border-t">
      <div className="bottom-workbench-header theme-panel px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="theme-text-primary flex items-center gap-2 text-sm font-bold">
              <ArrowDownToLine size={16} className="text-pixiu" />
              <span>Bottom Workbench</span>
            </div>
            <div className="theme-text-secondary mt-1 text-xs">
              {pdfFileName || '当前论文'} · {cards.length} 张工作台卡片 · {notes.length} 条边注
            </div>
          </div>
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="theme-button-secondary inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
          >
            {isCollapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {isCollapsed ? '展开工作台' : '收起工作台'}
          </button>
        </div>

        {!isCollapsed && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="theme-input flex min-w-[220px] items-center gap-2 rounded-full px-3 py-2 text-xs">
              <Search size={14} className="theme-text-muted" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索卡片标题、摘要、标签"
                className="theme-text-primary min-w-0 flex-1 bg-transparent outline-none"
              />
            </label>

            <button
              type="button"
              onClick={() => setActiveKind('all')}
              className={`workbench-filter-chip ${activeKind === 'all' ? 'workbench-filter-chip-active' : ''}`}
            >
              全部卡片
            </button>

            {kindOptions.map((option) => (
              <button
                key={option.kind}
                type="button"
                onClick={() => setActiveKind(option.kind)}
                className={`workbench-filter-chip ${activeKind === option.kind ? 'workbench-filter-chip-active' : ''}`}
              >
                {option.label} {option.count}
              </button>
            ))}
          </div>
        )}
      </div>

      {!isCollapsed && (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
            <section className="space-y-3">
              <div className="flex items-center justify-between gap-2 pt-2">
                <div className="theme-text-primary flex items-center gap-2 text-sm font-bold">
                  <Bookmark size={15} className="text-pixiu" />
                  Workbench Cards
                </div>
                <div className="theme-text-muted text-xs">{filteredCards.length} 张可见卡片</div>
              </div>

              {filteredCards.length > 0 ? (
                <div className="space-y-5">
                  {Object.entries(LANE_LABELS).map(([laneKey, laneLabel]) => (
                    <section key={laneKey} className="space-y-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="theme-text-primary text-sm font-semibold">{laneLabel}</div>
                        <div className="theme-text-muted text-xs">{groupedCards[laneKey]?.length || 0} 张</div>
                      </div>

                      {groupedCards[laneKey]?.length > 0 ? (
                        <div className="workbench-card-grid">
                          {groupedCards[laneKey].map((artifact) => {
                            const isEditing = editingArtifactId === artifact.artifactId;

                            return (
                              <article key={artifact.artifactId} className="theme-card workbench-artifact-card rounded-2xl p-4">
                                <div className="mb-3 flex items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <div className="theme-text-primary line-clamp-2 text-sm font-semibold">
                                      {artifact.title}
                                    </div>
                                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
                                      <span className="workbench-kind-chip">
                                        {KIND_LABELS[artifact.kind] || artifact.kind}
                                      </span>
                                      {Number.isFinite(artifact.pageIndex) && (
                                        <span className="theme-text-muted">p.{artifact.pageIndex + 1}</span>
                                      )}
                                    </div>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    {artifact.pinned && <Pin size={14} className="shrink-0 text-pixiu" />}
                                    <button
                                      type="button"
                                      onClick={() => (isEditing ? cancelEditingArtifact() : startEditingArtifact(artifact))}
                                      className="source-link-chip"
                                    >
                                      {isEditing ? <X size={12} /> : <Edit3 size={12} />}
                                      <span>{isEditing ? '取消编辑' : '编辑'}</span>
                                    </button>
                                  </div>
                                </div>

                                {isEditing ? (
                                  <div className="space-y-3">
                                    <input
                                      value={draftArtifact.title}
                                      onChange={(event) => setDraftArtifact((prev) => ({ ...prev, title: event.target.value }))}
                                      className="theme-input w-full rounded-xl px-3 py-2 text-sm"
                                      placeholder="卡片标题"
                                    />
                                    <textarea
                                      value={draftArtifact.summary}
                                      onChange={(event) => setDraftArtifact((prev) => ({ ...prev, summary: event.target.value }))}
                                      className="theme-input min-h-[96px] w-full rounded-xl px-3 py-2 text-sm"
                                      placeholder="卡片摘要"
                                    />
                                    <div className="grid gap-3 md:grid-cols-2">
                                      <select
                                        value={draftArtifact.lane}
                                        onChange={(event) => setDraftArtifact((prev) => ({ ...prev, lane: event.target.value }))}
                                        className="theme-input rounded-xl px-3 py-2 text-sm"
                                      >
                                        {Object.entries(LANE_LABELS).map(([value, label]) => (
                                          <option key={value} value={value}>{label}</option>
                                        ))}
                                      </select>
                                      <input
                                        value={draftArtifact.tagsText}
                                        onChange={(event) => setDraftArtifact((prev) => ({ ...prev, tagsText: event.target.value }))}
                                        className="theme-input rounded-xl px-3 py-2 text-sm"
                                        placeholder="标签，逗号分隔"
                                      />
                                    </div>
                                    <textarea
                                      value={draftArtifact.userNote}
                                      onChange={(event) => setDraftArtifact((prev) => ({ ...prev, userNote: event.target.value }))}
                                      className="theme-input min-h-[84px] w-full rounded-xl px-3 py-2 text-sm"
                                      placeholder="你的本地修订说明 / 后续写作提醒"
                                    />
                                    <div className="flex flex-wrap gap-2">
                                      <button
                                        type="button"
                                        onClick={() => saveEditingArtifact(artifact.artifactId)}
                                        className="source-link-chip"
                                      >
                                        <Check size={12} />
                                        <span>保存修改</span>
                                      </button>
                                      <button
                                        type="button"
                                        onClick={cancelEditingArtifact}
                                        className="source-link-chip"
                                      >
                                        <X size={12} />
                                        <span>放弃修改</span>
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <>
                                    <p className="theme-text-secondary line-clamp-5 text-sm leading-7">{artifact.summary}</p>

                                    {artifact.tags?.length > 0 && (
                                      <div className="mt-3 flex flex-wrap gap-2">
                                        {artifact.tags.map((tag) => (
                                          <span key={`${artifact.artifactId}-${tag}`} className="workbench-tag-chip">
                                            {tag}
                                          </span>
                                        ))}
                                      </div>
                                    )}

                                    {artifact.userNote && (
                                      <div className="theme-card-soft mt-3 rounded-xl px-3 py-2 text-sm leading-6 theme-text-secondary">
                                        {artifact.userNote}
                                      </div>
                                    )}

                                    <div className="mt-4 flex flex-wrap gap-2">
                                      <button
                                        type="button"
                                        onClick={() => onToggleArtifactPinned?.(artifact.artifactId)}
                                        className="source-link-chip"
                                      >
                                        {artifact.pinned ? '取消置顶' : '置顶'}
                                      </button>
                                      {artifact.sourceAnchorId && (
                                        <button
                                          type="button"
                                          onClick={() => onJumpToArtifactSource?.(artifact)}
                                          className="source-link-chip"
                                        >
                                          回到原文
                                        </button>
                                      )}
                                      <button
                                        type="button"
                                        onClick={() => onSaveArtifactAsNote?.(artifact)}
                                        className="source-link-chip"
                                      >
                                        保存为边注
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => onRemoveArtifact?.(artifact.artifactId)}
                                        className="theme-danger-button inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs"
                                      >
                                        <Trash2 size={12} />
                                        删除
                                      </button>
                                    </div>
                                  </>
                                )}
                              </article>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="theme-empty-state rounded-2xl px-4 py-3 text-sm">
                          这个泳道里还没有卡片。
                        </div>
                      )}
                    </section>
                  ))}
                </div>
              ) : (
                <div className="theme-empty-state rounded-2xl p-5 text-sm">
                  这里会沉淀高价值回答、研究发现、证据片段和翻译卡片。先在右侧结果卡上点“加入工作台”试试。
                </div>
              )}
            </section>

            <section className="space-y-3">
              <div className="flex items-center justify-between gap-2 pt-2">
                <div className="theme-text-primary flex items-center gap-2 text-sm font-bold">
                  <StickyNote size={15} className="text-pixiu" />
                  Margin Notes
                </div>
                <div className="theme-text-muted text-xs">{filteredNotes.length} 条可见边注</div>
              </div>

              {filteredNotes.length > 0 ? (
                <div className="space-y-3">
                  {filteredNotes.map((note) => (
                    <article key={note.id} className="theme-card rounded-2xl p-4">
                      <div className="mb-2 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="theme-text-primary line-clamp-2 text-sm font-semibold">
                            {normalizeText(note.text) || '未命名边注'}
                          </div>
                          <div className="theme-text-muted mt-1 text-[11px]">
                            {Number.isFinite(note.sourcePageIndex)
                              ? `p.${note.sourcePageIndex + 1}`
                              : Number.isFinite(note.pageNumber)
                                ? `p.${note.pageNumber + 1}`
                                : '原文边注'}
                          </div>
                        </div>
                      </div>

                      <p className="theme-note-quote mb-3 pl-3 text-sm italic">"{note.text}"</p>
                      <p className="theme-text-secondary line-clamp-4 text-sm leading-7">{note.aiInterpretation}</p>

                      <div className="mt-4 flex flex-wrap gap-2">
                        {note.sourceAnchorId && (
                          <button
                            type="button"
                            onClick={() => onJumpToNoteSource?.(note)}
                            className="source-link-chip"
                          >
                            回到原文
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => onCaptureNote?.(note)}
                          className="source-link-chip"
                        >
                          抓取到工作台
                        </button>
                        <button
                          type="button"
                          onClick={() => onDeleteNote?.(note.id)}
                          className="theme-danger-button inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs"
                        >
                          <Trash2 size={12} />
                          删除
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="theme-empty-state rounded-2xl p-5 text-sm">
                  这里会保留与原文绑定的边注。你可以从 PDF 划词解释或收藏对话，逐步把阅读过程沉淀下来。
                </div>
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  );
};

export default BottomWorkbench;
