import React, { useDeferredValue, useMemo, useState } from 'react';
import {
  ArrowDownToLine,
  Bookmark,
  Check,
  ChevronDown,
  ChevronUp,
  Download,
  Edit3,
  Eye,
  FileJson,
  FileText,
  Filter,
  FolderKanban,
  MessageSquare,
  Network,
  NotebookTabs,
  PenLine,
  Pin,
  Search,
  StickyNote,
  Trash2,
  X,
} from 'lucide-react';
import {
  buildWorkbenchJson,
  buildWorkbenchMarkdown,
  buildWorkbenchPlainText,
} from '../utils/workbenchExport.js';

const KIND_LABELS = {
  insight: '洞察卡片',
  'chat-answer': '问答卡片',
  'critical-summary': '批判总览',
  'critical-claimed': '作者主张',
  'critical-inferred': '真实贡献',
  'critical-critical': '批判结论',
  evidence: '证据卡片',
  'background-overview': '背景总览',
  'background-evidence': '背景依据',
  'research-snapshot': '研究快照',
  'research-finding': '研究发现',
  'translation-page': '页面译文',
  'paper-section': '篇章解构',
  'agent-report': 'Agent 报告',
  'agent-comparison': 'Agent 对比表',
  'agent-evidence': 'Agent 证据',
  'margin-note': '边注卡片',
};

const LANE_LABELS = {
  inbox: '收集箱',
  evidence: '证据池',
  argument: '观点区',
  draft: '写作草稿',
};

const LANE_SUMMARY = {
  inbox: {
    icon: Bookmark,
    hint: '先把值得留下的内容收进来，之后再统一整理。',
  },
  evidence: {
    icon: FileText,
    hint: '放可回到原文、可支持判断的依据与证据。',
  },
  argument: {
    icon: Network,
    hint: '放你已经形成的判断、比较与批判性结论。',
  },
  draft: {
    icon: PenLine,
    hint: '把准备写进汇报、综述或答辩的话先存成草稿。',
  },
};

const VIEW_OPTIONS = [
  { id: 'overview', label: '总览', icon: Eye },
  { id: 'cards', label: '整理卡片', icon: FolderKanban },
  { id: 'notes', label: '复盘边注', icon: NotebookTabs },
  { id: 'export', label: '成果导出', icon: Download },
];

const normalizeText = (value) => `${value ?? ''}`.trim();

const formatPageLabel = (pageIndex, fallbackText = '未定位页码') =>
  Number.isFinite(pageIndex) && pageIndex >= 0 ? `p.${pageIndex + 1}` : fallbackText;

const createEmptyDraftArtifact = () => ({
  title: '',
  summary: '',
  lane: 'inbox',
  tagsText: '',
  userNote: '',
});

const downloadTextFile = (filename, content, mimeType = 'text/plain;charset=utf-8') => {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return;
  }

  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
};

const buildExportBaseName = (pdfFileName) => {
  const cleaned = normalizeText(pdfFileName || 'paper-reading')
    .replace(/\.[^.]+$/, '')
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\s+/g, '-');

  return cleaned || 'paper-reading';
};

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
  const [activeView, setActiveView] = useState('overview');
  const [selectedArtifactId, setSelectedArtifactId] = useState(null);
  const [selectedNoteId, setSelectedNoteId] = useState(null);
  const [editingArtifactId, setEditingArtifactId] = useState(null);
  const [draftArtifact, setDraftArtifact] = useState(createEmptyDraftArtifact());
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
        card.userNote,
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

  const laneCounts = useMemo(
    () =>
      Object.keys(LANE_LABELS).reduce((map, laneKey) => {
        const nextMap = { ...map };
        nextMap[laneKey] = cards.filter((card) => (card.lane || 'inbox') === laneKey).length;
        return nextMap;
      }, {}),
    [cards],
  );

  const selectedArtifact = useMemo(() => {
    if (selectedArtifactId) {
      return filteredCards.find((artifact) => artifact.artifactId === selectedArtifactId) || null;
    }
    return filteredCards[0] || null;
  }, [filteredCards, selectedArtifactId]);

  const selectedNote = useMemo(() => {
    if (selectedNoteId !== null) {
      return filteredNotes.find((note) => note.id === selectedNoteId) || null;
    }
    return filteredNotes[0] || null;
  }, [filteredNotes, selectedNoteId]);

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
    setDraftArtifact(createEmptyDraftArtifact());
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

  const baseExportName = buildExportBaseName(pdfFileName);
  const markdownExport = useMemo(
    () =>
      buildWorkbenchMarkdown({
        pdfFileName,
        cards,
        notes,
        laneLabels: LANE_LABELS,
        kindLabels: KIND_LABELS,
      }),
    [cards, notes, pdfFileName],
  );
  const jsonExport = useMemo(
    () =>
      buildWorkbenchJson({
        pdfFileName,
        cards,
        notes,
      }),
    [cards, notes, pdfFileName],
  );
  const plainTextExport = useMemo(
    () =>
      buildWorkbenchPlainText({
        pdfFileName,
        cards,
        notes,
      }),
    [cards, notes, pdfFileName],
  );

  const workbenchStats = [
    { label: '工作台卡片', value: cards.length, icon: Bookmark },
    { label: '边注记录', value: notes.length, icon: StickyNote },
    { label: '可回到原文', value: cards.filter((card) => card.sourceAnchorId).length, icon: FileText },
    { label: '已形成观点', value: laneCounts.argument, icon: Network },
  ];

  const overviewHighlights = [
    {
      title: '先收集',
      description: '把问答、批判阅读、背景补课和深度研究里的高价值内容先放进工作台。',
      count: laneCounts.inbox,
      lane: 'inbox',
    },
    {
      title: '再整理',
      description: '把证据、观点和写作草稿分开放，避免所有卡片都混成一堆。',
      count: laneCounts.evidence + laneCounts.argument + laneCounts.draft,
      lane: 'argument',
    },
    {
      title: '最后导出',
      description: '把今天的研读成果导出成 Markdown 或 JSON，方便汇报、归档和二次加工。',
      count: cards.length + notes.length,
      lane: 'draft',
    },
  ];

  const renderArtifactInspector = () => {
    if (!selectedArtifact) {
      return (
        <div className="theme-empty-state rounded-3xl p-5 text-sm">
          暂无卡片
        </div>
      );
    }

    const isEditing = editingArtifactId === selectedArtifact.artifactId;

    return (
      <section className="theme-card workbench-inspector rounded-3xl p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="workbench-kind-chip">{KIND_LABELS[selectedArtifact.kind] || selectedArtifact.kind}</span>
              <span className="theme-text-muted text-xs">{formatPageLabel(selectedArtifact.pageIndex)}</span>
              {selectedArtifact.pinned && <span className="workbench-pin-badge">已置顶</span>}
            </div>
            <h3 className="theme-text-primary mt-3 text-base font-bold">
              {selectedArtifact.title || '未命名卡片'}
            </h3>
          </div>
          <button
            type="button"
            onClick={() => (isEditing ? cancelEditingArtifact() : startEditingArtifact(selectedArtifact))}
            className="source-link-chip"
          >
            {isEditing ? <X size={12} /> : <Edit3 size={12} />}
            <span>{isEditing ? '取消编辑' : '编辑卡片'}</span>
          </button>
        </div>

        {isEditing ? (
          <div className="mt-4 space-y-3">
            <input
              value={draftArtifact.title}
              onChange={(event) => setDraftArtifact((prev) => ({ ...prev, title: event.target.value }))}
              className="theme-input w-full rounded-2xl px-3 py-2.5 text-sm"
              placeholder="卡片标题"
            />
            <textarea
              value={draftArtifact.summary}
              onChange={(event) => setDraftArtifact((prev) => ({ ...prev, summary: event.target.value }))}
              className="theme-input min-h-[96px] w-full rounded-2xl px-3 py-2.5 text-sm"
              placeholder="卡片摘要"
            />
            <div className="grid gap-3 md:grid-cols-2">
              <select
                value={draftArtifact.lane}
                onChange={(event) => setDraftArtifact((prev) => ({ ...prev, lane: event.target.value }))}
                className="theme-input rounded-2xl px-3 py-2.5 text-sm"
              >
                {Object.entries(LANE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <input
                value={draftArtifact.tagsText}
                onChange={(event) => setDraftArtifact((prev) => ({ ...prev, tagsText: event.target.value }))}
                className="theme-input rounded-2xl px-3 py-2.5 text-sm"
                placeholder="标签，用逗号分隔"
              />
            </div>
            <textarea
              value={draftArtifact.userNote}
              onChange={(event) => setDraftArtifact((prev) => ({ ...prev, userNote: event.target.value }))}
              className="theme-input min-h-[120px] w-full rounded-2xl px-3 py-2.5 text-sm"
              placeholder="你自己的判断、后续写作提醒或答辩要点"
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => saveEditingArtifact(selectedArtifact.artifactId)}
                className="source-link-chip"
              >
                <Check size={12} />
                <span>保存修改</span>
              </button>
              <button type="button" onClick={cancelEditingArtifact} className="source-link-chip">
                <X size={12} />
                <span>放弃修改</span>
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="theme-text-secondary mt-4 text-sm leading-7">
              {selectedArtifact.summary || '暂无摘要'}
            </p>

            {selectedArtifact.tags?.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {selectedArtifact.tags.map((tag) => (
                  <span key={`${selectedArtifact.artifactId}-${tag}`} className="workbench-tag-chip">
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {selectedArtifact.userNote && (
              <div className="theme-card-soft mt-4 rounded-2xl px-4 py-3">
                <div className="theme-text-primary text-xs font-semibold">我的补充判断</div>
                <div className="theme-text-secondary mt-2 text-sm leading-7">{selectedArtifact.userNote}</div>
              </div>
            )}

            {selectedArtifact.content && (
              <div className="theme-card-soft mt-4 rounded-2xl px-4 py-3">
                <div className="theme-text-primary text-xs font-semibold">详细内容</div>
                <div className="theme-text-secondary mt-2 whitespace-pre-wrap text-sm leading-7">
                  {selectedArtifact.content}
                </div>
              </div>
            )}

            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onToggleArtifactPinned?.(selectedArtifact.artifactId)}
                className="source-link-chip"
              >
                <Pin size={12} />
                <span>{selectedArtifact.pinned ? '取消置顶' : '置顶卡片'}</span>
              </button>
              {selectedArtifact.sourceAnchorId && (
                <button
                  type="button"
                  onClick={() => onJumpToArtifactSource?.(selectedArtifact)}
                  className="source-link-chip"
                >
                  <MessageSquare size={12} />
                  <span>回到原文</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => onSaveArtifactAsNote?.(selectedArtifact)}
                className="source-link-chip"
              >
                <StickyNote size={12} />
                <span>转为边注</span>
              </button>
              <button
                type="button"
                onClick={() => onRemoveArtifact?.(selectedArtifact.artifactId)}
                className="theme-danger-button inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs"
              >
                <Trash2 size={12} />
                删除
              </button>
            </div>
          </>
        )}
      </section>
    );
  };

  const renderNoteInspector = () => {
    if (!selectedNote) {
      return (
        <div className="theme-empty-state rounded-3xl p-5 text-sm">
          暂无边注
        </div>
      );
    }

    const notePageIndex = Number.isFinite(selectedNote.sourcePageIndex) ? selectedNote.sourcePageIndex : selectedNote.pageNumber;

    return (
      <section className="theme-card workbench-inspector rounded-3xl p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <span className="workbench-kind-chip">边注记录</span>
            <h3 className="theme-text-primary mt-3 text-base font-bold">
              {normalizeText(selectedNote.text) || '未命名边注'}
            </h3>
            <div className="theme-text-muted mt-2 text-xs">{formatPageLabel(notePageIndex, '原文边注')}</div>
          </div>
        </div>

        <div className="theme-note-quote mt-4 pl-3 text-sm italic">
          “{normalizeText(selectedNote.text) || '暂无原文片段'}”
        </div>

        <div className="theme-card-soft mt-4 rounded-2xl px-4 py-3">
          <div className="theme-text-primary text-xs font-semibold">当前理解</div>
          <div className="theme-text-secondary mt-2 text-sm leading-7">
            {selectedNote.aiInterpretation || '暂无解释'}
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          {selectedNote.sourceAnchorId && (
            <button type="button" onClick={() => onJumpToNoteSource?.(selectedNote)} className="source-link-chip">
              <MessageSquare size={12} />
              <span>回到原文</span>
            </button>
          )}
          <button type="button" onClick={() => onCaptureNote?.(selectedNote)} className="source-link-chip">
            <Bookmark size={12} />
            <span>抓取到工作台</span>
          </button>
          <button
            type="button"
            onClick={() => onDeleteNote?.(selectedNote.id)}
            className="theme-danger-button inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs"
          >
            <Trash2 size={12} />
            删除
          </button>
        </div>
      </section>
    );
  };

  return (
    <div className="bottom-workbench theme-panel theme-border flex h-full flex-col border-t">
      <div className="bottom-workbench-header theme-panel px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="theme-text-primary flex items-center gap-2 text-sm font-bold">
              <ArrowDownToLine size={16} className="text-pixiu" />
              <span>研读工作台</span>
            </div>
            <div className="theme-text-secondary mt-1 text-xs">
              {pdfFileName || '当前论文'} · 把收集、整理和导出放进一条清晰链路里
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!isCollapsed && (
              <button
                type="button"
                onClick={() => downloadTextFile(`${baseExportName}-paper-reading.md`, markdownExport, 'text/markdown;charset=utf-8')}
                className="theme-button-secondary inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
              >
                <Download size={14} />
                快速导出
              </button>
            )}
            <button
              type="button"
              onClick={onToggleCollapsed}
              className="theme-button-secondary inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
            >
              {isCollapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {isCollapsed ? '展开工作台' : '收起工作台'}
            </button>
          </div>
        </div>

        {!isCollapsed && (
          <>
            <div className="mt-3 grid gap-2 md:grid-cols-4">
              {workbenchStats.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} className="theme-card-soft flex items-center gap-3 rounded-2xl px-3 py-2.5">
                    <Icon size={14} className="text-pixiu" />
                    <div className="min-w-0">
                      <div className="theme-text-primary text-sm font-semibold">{item.value}</div>
                      <div className="theme-text-muted text-[11px]">{item.label}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              {VIEW_OPTIONS.map((option) => {
                const Icon = option.icon;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setActiveView(option.id)}
                    className={`workbench-filter-chip ${activeView === option.id ? 'workbench-filter-chip-active' : ''}`}
                  >
                    <Icon size={13} />
                    {option.label}
                  </button>
                );
              })}
            </div>

            {(activeView === 'cards' || activeView === 'notes') && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <label className="theme-input flex min-w-[240px] items-center gap-2 rounded-full px-3 py-2 text-xs">
                  <Search size={14} className="theme-text-muted" />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder={activeView === 'cards' ? '搜索标题、摘要、标签' : '搜索边注片段、解释'}
                    className="theme-text-primary min-w-0 flex-1 bg-transparent outline-none"
                  />
                </label>

                {activeView === 'cards' && (
                  <>
                    <span className="theme-text-muted inline-flex items-center gap-1 text-xs">
                      <Filter size={12} />
                      类型筛选
                    </span>
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
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {!isCollapsed && (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          {activeView === 'overview' && (
            <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <section className="space-y-4 pt-3">
                <div className="grid gap-3 md:grid-cols-3">
                  {overviewHighlights.map((item) => (
                    <button
                      key={item.title}
                      type="button"
                      onClick={() => setActiveView(item.title === '最后导出' ? 'export' : 'cards')}
                      className="theme-card workbench-stage-card rounded-3xl p-4 text-left transition"
                    >
                      <div className="theme-text-primary text-sm font-semibold">{item.title}</div>
                      <div className="theme-text-secondary mt-2 text-sm leading-6">{item.description}</div>
                      <div className="mt-4 flex items-center justify-between text-xs">
                        <span className="rounded-full bg-pixiu/10 px-2 py-1 font-semibold text-pixiu">当前条目 {item.count}</span>
                        <span className="theme-text-muted">进入</span>
                      </div>
                    </button>
                  ))}
                </div>

                <div className="theme-card rounded-3xl p-5">
                  <div className="theme-text-primary text-sm font-bold">当前整理建议</div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {Object.entries(LANE_LABELS).map(([laneKey, laneLabel]) => {
                      const LaneIcon = LANE_SUMMARY[laneKey].icon;
                      return (
                        <div key={laneKey} className="theme-card-soft rounded-2xl p-4">
                          <div className="flex items-center justify-between gap-2">
                            <div className="theme-text-primary flex items-center gap-2 text-sm font-semibold">
                              <LaneIcon size={14} className="text-pixiu" />
                              {laneLabel}
                            </div>
                            <span className="theme-text-muted text-xs">{laneCounts[laneKey]} 张</span>
                          </div>
                          <div className="theme-text-secondary mt-2 text-sm leading-6">{LANE_SUMMARY[laneKey].hint}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </section>

              <section className="space-y-4 pt-3">
                <div className="theme-card rounded-3xl p-5">
                  <div className="theme-text-primary text-sm font-bold">导出前预检</div>
                  <div className="mt-3 space-y-3 text-sm">
                    <div className="workbench-check-row">
                      <span>至少有 1 张工作台卡片</span>
                      <strong>{cards.length > 0 ? '已满足' : '待补充'}</strong>
                    </div>
                    <div className="workbench-check-row">
                      <span>至少形成 1 条观点或草稿</span>
                      <strong>{laneCounts.argument + laneCounts.draft > 0 ? '已满足' : '待整理'}</strong>
                    </div>
                    <div className="workbench-check-row">
                      <span>有边注或原文证据可追溯</span>
                      <strong>{notes.length > 0 || laneCounts.evidence > 0 ? '已满足' : '待补充'}</strong>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveView('export')}
                    className="mt-4 rounded-full bg-pixiu px-4 py-2 text-sm font-semibold text-white"
                  >
                    去成果导出
                  </button>
                </div>
              </section>
            </div>
          )}

          {activeView === 'cards' && (
            <div className="workbench-two-pane pt-3">
              <section className="space-y-4">
                {Object.entries(LANE_LABELS).map(([laneKey, laneLabel]) => {
                  const laneCards = groupedCards[laneKey] || [];
                  const LaneIcon = LANE_SUMMARY[laneKey].icon;

                  return (
                    <div key={laneKey} className="theme-card rounded-3xl p-4">
                      <div className="flex items-center justify-between gap-2">
                        <div className="theme-text-primary flex items-center gap-2 text-sm font-semibold">
                          <LaneIcon size={14} className="text-pixiu" />
                          {laneLabel}
                        </div>
                        <div className="theme-text-muted text-xs">{laneCards.length} 张</div>
                      </div>
                      <div className="theme-text-muted mt-1 text-[11px]">{LANE_SUMMARY[laneKey].hint}</div>

                      {laneCards.length > 0 ? (
                        <div className="mt-3 space-y-2">
                          {laneCards.map((artifact) => (
                            <button
                              key={artifact.artifactId}
                              type="button"
                              onClick={() => {
                                setSelectedArtifactId(artifact.artifactId);
                                if (editingArtifactId && editingArtifactId !== artifact.artifactId) {
                                  cancelEditingArtifact();
                                }
                              }}
                              className={`workbench-list-item ${
                                selectedArtifact?.artifactId === artifact.artifactId ? 'workbench-list-item-active' : ''
                              }`}
                            >
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="theme-text-primary truncate text-sm font-semibold">
                                    {artifact.title || '未命名卡片'}
                                  </span>
                                  {artifact.pinned && <Pin size={12} className="shrink-0 text-pixiu" />}
                                </div>
                                <div className="theme-text-secondary mt-1 line-clamp-2 text-xs leading-5">
                                  {artifact.summary || '暂无摘要'}
                                </div>
                              </div>
                              <div className="theme-text-muted shrink-0 text-[11px]">
                                {formatPageLabel(artifact.pageIndex)}
                              </div>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <div className="theme-empty-state mt-3 rounded-2xl px-4 py-3 text-sm">这个分区里还没有内容。</div>
                      )}
                    </div>
                  );
                })}
              </section>

              {renderArtifactInspector()}
            </div>
          )}

          {activeView === 'notes' && (
            <div className="workbench-two-pane pt-3">
              <section className="theme-card rounded-3xl p-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="theme-text-primary flex items-center gap-2 text-sm font-semibold">
                    <StickyNote size={14} className="text-pixiu" />
                    边注列表
                  </div>
                  <div className="theme-text-muted text-xs">{filteredNotes.length} 条</div>
                </div>

                {filteredNotes.length > 0 ? (
                  <div className="mt-3 space-y-2">
                    {filteredNotes.map((note) => {
                      const pageIndex = Number.isFinite(note.sourcePageIndex) ? note.sourcePageIndex : note.pageNumber;

                      return (
                        <button
                          key={note.id}
                          type="button"
                          onClick={() => setSelectedNoteId(note.id)}
                          className={`workbench-list-item ${selectedNote?.id === note.id ? 'workbench-list-item-active' : ''}`}
                        >
                          <div className="min-w-0">
                            <div className="theme-text-primary truncate text-sm font-semibold">
                              {normalizeText(note.text) || '未命名边注'}
                            </div>
                            <div className="theme-text-secondary mt-1 line-clamp-2 text-xs leading-5">
                              {note.aiInterpretation || '暂无解释'}
                            </div>
                          </div>
                          <div className="theme-text-muted shrink-0 text-[11px]">{formatPageLabel(pageIndex, '原文边注')}</div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="theme-empty-state mt-3 rounded-2xl p-5 text-sm">
                    暂无边注
                  </div>
                )}
              </section>

              {renderNoteInspector()}
            </div>
          )}

          {activeView === 'export' && (
            <div className="grid gap-4 pt-3 xl:grid-cols-[0.9fr_1.1fr]">
              <section className="space-y-4">
                <div className="theme-card rounded-3xl p-5">
                  <div className="theme-text-primary text-sm font-bold">成果导出</div>
                  <div className="theme-text-secondary mt-2 text-sm leading-6">
                    导出不会修改后端数据，只会把当前前端已沉淀的卡片与边注整理成文件。
                  </div>

                  <div className="mt-4 space-y-3">
                    <button
                      type="button"
                      onClick={() => downloadTextFile(`${baseExportName}-paper-reading.md`, markdownExport, 'text/markdown;charset=utf-8')}
                      className="workbench-export-button"
                    >
                      <FileText size={16} />
                      <div className="min-w-0">
                        <div className="font-semibold">导出 Markdown 报告</div>
                        <div className="text-xs opacity-80">适合汇报、答辩稿整理和继续手动编辑</div>
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => downloadTextFile(`${baseExportName}-workspace.json`, jsonExport, 'application/json;charset=utf-8')}
                      className="workbench-export-button"
                    >
                      <FileJson size={16} />
                      <div className="min-w-0">
                        <div className="font-semibold">导出 JSON 快照</div>
                        <div className="text-xs opacity-80">适合二次加工、备份或后续程序处理</div>
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => downloadTextFile(`${baseExportName}-reading-summary.txt`, plainTextExport)}
                      className="workbench-export-button"
                    >
                      <ArrowDownToLine size={16} />
                      <div className="min-w-0">
                        <div className="font-semibold">导出纯文本摘要</div>
                        <div className="text-xs opacity-80">适合快速复制到聊天、邮件或即时汇报中</div>
                      </div>
                    </button>
                  </div>
                </div>
              </section>

              <section className="theme-card rounded-3xl p-5">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="theme-text-primary text-sm font-bold">Markdown 预览</div>
                    <div className="theme-text-muted mt-1 text-xs">预览当前将被导出的主要成果结构</div>
                  </div>
                </div>
                <pre className="workbench-export-preview mt-4">{markdownExport}</pre>
              </section>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default BottomWorkbench;
