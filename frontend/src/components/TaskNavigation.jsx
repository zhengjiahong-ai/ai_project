import React, { useLayoutEffect, useRef, useState } from 'react';
import { Plus, ChevronLeft, ChevronRight, FileText, NotebookPen, Search, SlidersHorizontal, X } from 'lucide-react';
import { taskDocumentNavigation } from '../utils/taskDocumentNavigation';
import { documentKind, paperShortName } from '../utils/documentPresentation';
import { documentSearchText, searchExcerpt, readNavigationVisits, rememberNavigationVisit } from '../utils/navigationSearch';
import WorkbenchPopover from './WorkbenchPopover';
import LearningHistory, { learningSearchText } from './LearningHistory';
import './TaskNavigationDetails.css';

const processingLabel = paper => {
  if (paper?.processingStatus === 'queued') return '等待解析';
  if (paper?.processingStatus === 'parsing') return '正在解析';
  if (paper?.questionReady === false) return ['failed', 'interrupted', 'degraded'].includes(paper.processingStatus) ? '正文未就绪 · 打开处理' : '正文未就绪';
  return '';
};

export default function TaskNavigation({ tasks, activeTask, papers, collapsed, onToggle,
  onSelectTask, onCreateTask, onOpenPaper, onAddPaper, onRemovePaper, onOpenArtifact, onCreateNote,
  onUpload, uploading = false, onCancelUpload, taskControlsInHeader = false, learningRecords = [], onOpenLearning, onOpenTaskDocument, selectedDocumentId, selectedLearningId, children }) {
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchScope, setSearchScope] = useState('current');
  const [visits, setVisits] = useState(() => ({ taskId: activeTask?.id, items: readNavigationVisits(activeTask?.id) }));
  const [type, setType] = useState('all');
  const [papersOpen, setPapersOpen] = useState(true);
  const [removedPaper, setRemovedPaper] = useState(null);
  const paperListRef = useRef(null), recordListRef = useRef(null), searchScroll = useRef(null);
  useLayoutEffect(() => { searchScroll.current = null; }, [activeTask?.id]);
  const searching = Boolean(query.trim());
  useLayoutEffect(() => {
    if (!searching && searchScroll.current) {
      if (paperListRef.current) paperListRef.current.scrollTop = searchScroll.current.papers;
      if (recordListRef.current) recordListRef.current.scrollTop = searchScroll.current.records;
      searchScroll.current = null;
    }
  }, [searching]);
  const changeQuery = value => {
    if (!query.trim() && value.trim()) searchScroll.current = { papers: paperListRef.current?.scrollTop || 0, records: recordListRef.current?.scrollTop || 0 };
    setQuery(value);
  };
  const operationEpoch = useRef(0), busyRef = useRef(false);
  React.useEffect(() => { operationEpoch.current += 1; busyRef.current = false; setBusy(false); setError(''); setQuery(''); setSearchOpen(false); setType('all'); setAdding(false); setRemovedPaper(null); }, [activeTask?.id]);
  React.useEffect(() => {
    const taskId = activeTask?.id;
    const visit = selectedDocumentId ? { kind: 'document', id: selectedDocumentId }
      : selectedLearningId ? { kind: 'learning', id: selectedLearningId }
        : activeTask?.focusedPaperId ? { kind: 'paper', id: activeTask.focusedPaperId } : null;
    setVisits({ taskId, items: visit ? rememberNavigationVisit(taskId, visit) : readNavigationVisits(taskId) });
  }, [activeTask?.id, activeTask?.focusedPaperId, selectedDocumentId, selectedLearningId]);
  const matches = value => !query.trim() || `${value || ''}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
  const kindOf = item => documentKind(item, activeTask);
  const typeLabels = { note: '笔记', learning: '学习', research: '报告', compare: '比较', translation: '译文', critique: '批判', background: '补课', compose: '组合', artifact: '成果' };
  const allDocuments = taskDocumentNavigation(activeTask, papers);
  const documents = allDocuments.filter(({ item, title }) => matches(`${title} ${documentSearchText(item)}`) && (type === 'all' || kindOf(item) === type));
  const otherDocuments = searching && searchScope === 'all' && onOpenTaskDocument ? tasks.filter(task => task.id !== activeTask?.id)
    .flatMap(task => taskDocumentNavigation(task, papers).filter(({ item, title }) => matches(`${title} ${documentSearchText(item)}`)
      && (type === 'all' || documentKind(item, task) === type)).map(entry => ({ ...entry, owner: task }))) : [];
  const paperIds = (activeTask?.paperIds || []).filter(id => {
    const paper = papers.find(item => item.id === id);
    return matches(`${paper?.title || ''} ${paper?.filename || ''} ${id}`);
  });
  const matchingLearning = ['all', 'learning'].includes(type) ? learningRecords.filter(activity => matches(learningSearchText(activity, papers))) : [];
  const remember = (kind, id) => setVisits({ taskId: activeTask?.id, items: rememberNavigationVisit(activeTask?.id, { kind, id }) });
  const finishSearch = () => { changeQuery(''); setSearchOpen(false); };
  const recentItems = (visits.taskId === activeTask?.id ? visits.items : []).flatMap(visit => {
    if (visit.kind === 'paper') {
      const paper = papers.find(item => item.id === visit.id && activeTask?.paperIds.includes(item.id));
      return paper ? [{ ...visit, title: paperShortName(paper), label: '论文', open: () => onOpenPaper(paper.id) }] : [];
    }
    if (visit.kind === 'document') {
      const entry = allDocuments.find(({ item }) => (item.id || item.artifactId) === visit.id);
      return entry ? [{ ...visit, title: entry.title, label: typeLabels[kindOf(entry.item)] || '成果', open: () => onOpenArtifact(entry.item) }] : [];
    }
    const activity = learningRecords.find(item => (item.activityId || item.id) === visit.id);
    return activity && onOpenLearning ? [{ ...visit, title: activity.title || activity.goal || `${paperShortName(papers.find(paper => paper.id === (activity.pdfId || activity.primaryPaperId)), '论文')} · 学习记录`, label: '学习', open: () => onOpenLearning(activity) }] : [];
  }).slice(0, 4);
  const noSearchResults = query.trim() && !paperIds.length && !documents.length && !matchingLearning.length && !otherDocuments.length;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const perform = async (action) => {
    if (busyRef.current) return;
    busyRef.current = true;
    const epoch = ++operationEpoch.current;
    const isCurrent = () => epoch === operationEpoch.current;
    setBusy(true); setError('');
    try { await action(isCurrent); } catch (failure) { if (isCurrent()) setError(failure.message || '操作失败，请重试'); }
    finally { if (isCurrent()) { busyRef.current = false; setBusy(false); } }
  };
  return <aside className={`workbench-navigation theme-panel theme-border ${collapsed ? 'is-collapsed' : ''}`} aria-label="任务导航">
    <div className="workbench-navigation-head">
      {!collapsed && !taskControlsInHeader && <select aria-label="当前任务" value={activeTask?.id || ''} onChange={(event) => onSelectTask(event.target.value)} className="theme-input min-w-0 flex-1 rounded p-2 text-sm">
        {!activeTask && <option value="">选择任务</option>}
        {tasks.map((task) => <option key={task.id} value={task.id}>{task.title || '未命名任务'}</option>)}
      </select>}
      {!collapsed && taskControlsInHeader && <span className="workbench-navigation-caption">任务内容</span>}
      <button type="button" onClick={onToggle} className="pixiu-icon-action" aria-label={collapsed ? '展开导航' : '收起导航'}>{collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}</button>
    </div>
    {!taskControlsInHeader && <button type="button" disabled={busy} onClick={() => perform(() => onCreateTask())} className="theme-text-primary m-2 flex items-center gap-2 rounded p-2 text-sm" aria-label="新任务"><Plus size={16} />{!collapsed && '新任务'}</button>}
    {!collapsed && <>
      <div className="workbench-navigation-search"><Search size={15} /><input className="unified-nav-search" aria-label="搜索材料与记录" placeholder="搜索本任务" value={query} onFocus={() => setSearchOpen(true)} onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); finishSearch(); } }} onChange={event => { setSearchOpen(true); changeQuery(event.target.value); }} />{(searchOpen || searching) && <button type="button" aria-label="结束导航搜索" onClick={finishSearch}><X size={14} /></button>}</div>
      {searching && <p className="workbench-search-scope">搜索本任务已加载的材料名称、成果与学习记录</p>}
      {searchOpen && !searching && <section className="workbench-recent-visits" aria-label="最近访问"><h2>最近访问</h2>{recentItems.length ? recentItems.map(item => <button type="button" key={`${item.kind}:${item.id}`} onClick={() => { remember(item.kind, item.id); finishSearch(); item.open(); }}><span>{item.title}</span><small>{item.label}</small></button>) : <p>打开过的材料与记录会出现在这里。</p>}</section>}
      {searching && onOpenTaskDocument && <label className="workbench-menu-caption">搜索范围 <select aria-label="搜索范围" className="theme-input" value={searchScope} onChange={event => setSearchScope(event.target.value)}><option value="current">当前任务</option><option value="all">所有任务的笔记与成果</option></select></label>}
      {otherDocuments.length > 0 && <section aria-label="其他任务的搜索结果"><h3 className="workbench-menu-caption">其他任务</h3>{otherDocuments.map(({ item, title, owner }) => <button type="button" className="workbench-record-link theme-text-primary" key={`${owner.id}:${item.id || item.artifactId}`} onClick={() => { finishSearch(); onOpenTaskDocument(owner.id, item); }}><NotebookPen size={15} /><span className="min-w-0"><span className="block truncate">{title}</span><small className="theme-text-muted">{owner.title || '未命名任务'}</small><span className="workbench-search-excerpt">{searchExcerpt(documentSearchText(item), query)}</span></span></button>)}</section>}
      {uploading && <div className="workbench-upload-state" role="status"><span>正在上传…</span>{onCancelUpload && <button type="button" onClick={onCancelUpload}>取消上传</button>}</div>}
      {error && <p role="alert" className="mb-3 text-sm text-red-600">{error}</p>}
      <div className={`workbench-navigation-lists ${!papersOpen && !query ? 'papers-collapsed' : ''}`}>
      <section className="workbench-navigation-papers" aria-label="论文与材料列表">
      <div className="workbench-section-head"><button type="button" className="workbench-section-toggle" aria-expanded={papersOpen || Boolean(query)} onClick={() => setPapersOpen(value => !value)}><ChevronRight size={13} className={papersOpen || query ? 'expanded' : ''} />论文与材料 <span>{activeTask?.paperIds.length || 0}</span></button>
        {onUpload ? <WorkbenchPopover label="添加论文" trigger={<Plus size={16} />}>
          {close => <><button type="button" disabled={uploading} onClick={() => { onUpload(); close(); }}>{uploading ? '上传中…' : '上传 PDF'}</button><button type="button" disabled={!activeTask} onClick={() => { setAdding(value => !value); setPapersOpen(true); close(); }}>选择已有论文</button></>}
        </WorkbenchPopover> : <button type="button" disabled={!activeTask} onClick={() => setAdding(!adding)} aria-label="添加已有论文"><Plus size={16} /></button>}
      </div>
      {(papersOpen || query) && <div ref={paperListRef} className="workbench-paper-list">
      {paperIds.map((id) => {
        const paper = papers.find((item) => item.id === id);
        return <div key={id} className="workbench-paper-row">
          <button type="button" title={paper?.title || paper?.filename || id} aria-label={paperShortName(paper, id)} aria-current={!selectedDocumentId && !selectedLearningId && activeTask.focusedPaperId === id ? 'page' : undefined} onClick={() => { remember('paper', id); finishSearch(); onOpenPaper(id); }} className="workbench-record-link theme-text-primary"><FileText size={15} /><span className="workbench-paper-text"><span>{paperShortName(paper, id)}</span>{processingLabel(paper) && <small>{processingLabel(paper)}</small>}</span></button>
          <WorkbenchPopover label={`论文操作：${paper?.title || paper?.filename || id}`}>
            {close => <><p className="workbench-menu-caption">移出当前任务，保留论文文件。</p><button type="button" disabled={busy} aria-label={`移出任务：${paper?.title || paper?.filename || id}`} onClick={() => perform(async isCurrent => { await onRemovePaper(id); if (isCurrent()) { setRemovedPaper({ id, title: paperShortName(paper, id) }); close(); } })}>移出任务</button></>}
          </WorkbenchPopover>
        </div>;
      })}
      {adding && <div className="theme-border my-2 rounded border p-2">
        {papers.filter((paper) => !activeTask?.paperIds.includes(paper.id)).map((paper) => <button type="button" disabled={busy} key={paper.id} onClick={() => perform(() => onAddPaper(paper.id))} className="theme-text-primary block w-full truncate py-2 text-left text-sm">{paper.title || paper.filename}</button>)}
        {!papers.some((paper) => !activeTask?.paperIds.includes(paper.id)) && <p className="theme-text-muted text-xs">暂无其他论文，可上传新论文。</p>}
      </div>}
      {children}
      </div>}
      </section>
      <section className="workbench-navigation-records" aria-label="笔记与成果列表">
      <div className="workbench-section-head"><h2>笔记与成果</h2><div>
        {onCreateNote && <button type="button" aria-label="新建笔记" disabled={!activeTask || busy} onClick={() => perform(onCreateNote)}><Plus size={16} /></button>}
        <WorkbenchPopover label="筛选成果" trigger={<SlidersHorizontal size={15} />}><label className="workbench-menu-caption">成果类型
      <select className="unified-nav-filter" aria-label="成果类型" value={type} onChange={event => setType(event.target.value)}>
        <option value="all">全部记录</option><option value="note">笔记</option><option value="learning">学习记录</option><option value="research">研究报告</option><option value="compare">论文比较</option><option value="translation">译文</option><option value="critique">批判阅读</option><option value="background">补课</option><option value="compose">组合成果</option>
      </select></label></WorkbenchPopover></div></div>
      {type !== 'all' && <button type="button" className="workbench-filter-state" onClick={() => setType('all')}>{typeLabels[type] || '筛选'} · 清除筛选</button>}
      <div ref={recordListRef} className="workbench-record-list">
      {documents.map(({ item, title, detail, preview, date, index }) => <button type="button" aria-current={selectedDocumentId && selectedDocumentId === (item.id || item.artifactId) ? 'page' : undefined} key={item.id || item.artifactId || index} aria-label={[title, typeLabels[kindOf(item)] || '成果', detail].filter(Boolean).join(' · ')} title={[title, detail].filter(Boolean).join('\n')} onClick={() => { remember('document', item.id || item.artifactId); finishSearch(); onOpenArtifact(item); }} className="task-document-link theme-text-primary flex w-full items-center gap-2 rounded py-2 text-left text-sm"><NotebookPen size={15} className="shrink-0" /><span className="task-document-text min-w-0 flex-1"><span className="block truncate">{title}</span>{!searching && preview && <span className="task-document-preview theme-text-muted block truncate text-xs">{preview}</span>}{(date || detail) && <span className="theme-text-muted block truncate text-xs">{date || detail}</span>}{searching && <span className="workbench-search-excerpt">{searchExcerpt(documentSearchText(item), query)}</span>}</span><span className="task-document-type theme-text-muted">{typeLabels[kindOf(item)] || '成果'}</span></button>)}
      {!documents.length && type !== 'learning' && <p className="theme-text-muted text-xs">{query || type !== 'all' ? '没有匹配的成果' : '保存的内容会出现在这里'}</p>}
      {type === 'learning' && !matchingLearning.length && <p className="theme-text-muted text-xs">{query ? '没有匹配的学习记录' : '学习记录会出现在这里'}</p>}
      <LearningHistory key={activeTask?.id} activities={matchingLearning} papers={papers} onOpen={onOpenLearning && (activity => { remember('learning', activity.activityId || activity.id); finishSearch(); onOpenLearning(activity); })} searchActive={Boolean(query.trim())} searchQuery={query.trim()} selectedLearningId={selectedLearningId} />
      {noSearchResults && <p role="status" className="task-navigation-empty theme-text-muted">没有匹配的论文、成果或学习记录。请换个关键词，或调整成果类型。</p>}

      </div></section></div>
      {removedPaper && <div className="workbench-undo" role="status"><span>已移出 {removedPaper.title}</span><button type="button" disabled={busy} onClick={() => perform(async isCurrent => { await onAddPaper(removedPaper.id); if (isCurrent()) setRemovedPaper(null); })}>撤销</button></div>}
    </>}
  </aside>;
}
