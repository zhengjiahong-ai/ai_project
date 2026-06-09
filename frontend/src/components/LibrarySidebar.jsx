import React, { useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock3,
  FileText,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import { getPaperStudyProgress } from '../utils/studyProgress.js';

const statusOptions = ['全部', '已解析', '索引异常'];

const formatDateTime = (timestamp) => {
  if (!timestamp) return '未记录';

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '未记录';

  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
};

const getPaperStatus = (paper) => {
  if (paper?.parseStatus) return paper.parseStatus;
  if (paper?.ragIndexed === false) return '索引异常';
  return '已解析';
};

const statusStyle = (status) => {
  if (status === '索引异常') {
    return 'bg-amber-500/10 text-amber-600';
  }

  return 'bg-emerald-500/10 text-emerald-600';
};

const getCurrentPageLabel = (paper, currentPdfId, currentPage, currentTotalPages) => {
  const page = paper.id === currentPdfId ? currentPage : paper.currentPage;
  const total = paper.id === currentPdfId ? currentTotalPages : paper.totalPages;

  if (!page || !total) return '尚未定位页码';
  return `${page} / ${total} 页`;
};

const LibrarySidebar = ({
  isOpen,
  onClose,
  papers = [],
  currentPdfId,
  currentStudyProgressSnapshot = null,
  currentPage = 0,
  currentTotalPages = 0,
  onSelectPaper,
  onDeletePaper,
}) => {
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('全部');

  const filteredPapers = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return papers.filter((paper) => {
      const status = getPaperStatus(paper);
      const authors = Array.isArray(paper.authors) ? paper.authors.join(', ') : paper.authors || '';
      const searchable = `${paper.title || ''} ${paper.filename || ''} ${authors}`.toLowerCase();
      const matchesQuery = !normalizedQuery || searchable.includes(normalizedQuery);
      const matchesStatus = statusFilter === '全部' || status === statusFilter;

      return matchesQuery && matchesStatus;
    });
  }, [papers, query, statusFilter]);

  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 z-[70] bg-slate-950/35 backdrop-blur-sm transition-opacity" onClick={onClose} />
      <section className="theme-panel theme-border fixed left-1/2 top-8 z-[80] flex max-h-[88vh] w-[calc(100vw-2rem)] max-w-6xl -translate-x-1/2 flex-col rounded-lg border shadow-2xl">
        <header className="theme-panel-muted theme-border flex shrink-0 items-center justify-between border-b px-5 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-pixiu text-white">
              <BookOpen size={18} />
            </div>
            <div className="min-w-0">
              <h2 className="theme-text-primary text-base font-bold">论文库</h2>
              <p className="theme-text-muted text-xs">
                共 {papers.length} 篇论文，当前显示 {filteredPapers.length} 篇
              </p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="theme-icon-button rounded-md p-2 transition" title="关闭">
            <X size={20} />
          </button>
        </header>

        <div className="theme-panel theme-border flex shrink-0 flex-col gap-3 border-b px-5 py-3 lg:flex-row lg:items-center lg:justify-between">
          <label className="theme-input flex min-w-0 flex-1 items-center gap-2 rounded-md px-3 py-2 text-sm lg:max-w-md">
            <Search size={16} className="theme-text-muted shrink-0" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="min-w-0 flex-1 bg-transparent outline-none"
              placeholder="搜索标题、文件名或作者"
            />
          </label>

          <div className="theme-tab-group flex w-fit rounded-md p-1">
            {statusOptions.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setStatusFilter(option)}
                className={`rounded px-3 py-1.5 text-xs font-semibold transition ${
                  statusFilter === option ? 'theme-tab-active' : 'theme-tab'
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          {papers.length === 0 ? (
            <div className="theme-empty-state m-5 flex min-h-64 flex-col items-center justify-center rounded-lg p-8 text-center">
              <FileText size={28} className="mb-3 text-pixiu" />
              <h3 className="theme-text-primary text-sm font-bold">论文库暂时还没有内容</h3>
              <p className="theme-text-muted mt-2 max-w-sm text-sm">
                上传第一篇 PDF 后，这里会记录解析状态、研读完成度和最近阅读位置。
              </p>
            </div>
          ) : filteredPapers.length === 0 ? (
            <div className="theme-empty-state m-5 flex min-h-64 flex-col items-center justify-center rounded-lg p-8 text-center">
              <Search size={28} className="mb-3 text-pixiu" />
              <h3 className="theme-text-primary text-sm font-bold">没有匹配的论文</h3>
              <p className="theme-text-muted mt-2 text-sm">调整搜索词或筛选条件后再查看。</p>
            </div>
          ) : (
            <table className="w-full min-w-[1080px] border-separate border-spacing-0 text-left text-sm">
              <thead className="theme-panel-muted sticky top-0 z-10">
                <tr className="theme-text-muted text-xs">
                  <th className="theme-border border-b px-5 py-3 font-bold">论文</th>
                  <th className="theme-border border-b px-4 py-3 font-bold">作者</th>
                  <th className="theme-border border-b px-4 py-3 font-bold">研读完成度</th>
                  <th className="theme-border border-b px-4 py-3 font-bold">解析状态</th>
                  <th className="theme-border border-b px-4 py-3 font-bold">上传时间</th>
                  <th className="theme-border border-b px-4 py-3 font-bold">最近阅读</th>
                  <th className="theme-border border-b px-5 py-3 text-right font-bold">操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredPapers.map((paper) => {
                  const isActive = paper.id === currentPdfId;
                  const status = getPaperStatus(paper);
                  const progressModel = getPaperStudyProgress(
                    paper,
                    isActive ? currentStudyProgressSnapshot : null,
                  );
                  const authors = Array.isArray(paper.authors) ? paper.authors.join(', ') : paper.authors;

                  return (
                    <tr key={paper.id} className={isActive ? 'bg-pixiu/5' : 'theme-panel'}>
                      <td className="theme-border max-w-[24rem] border-b px-5 py-4">
                        <div className="flex min-w-0 items-start gap-3">
                          <FileText size={18} className="mt-0.5 shrink-0 text-pixiu" />
                          <div className="min-w-0">
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="theme-text-primary truncate font-semibold">
                                {paper.title || paper.filename || '未命名论文'}
                              </span>
                              {isActive && (
                                <span className="shrink-0 rounded-full bg-pixiu/10 px-2 py-0.5 text-[10px] font-bold text-pixiu">
                                  当前
                                </span>
                              )}
                            </div>
                            <p className="theme-text-muted mt-1 truncate text-xs">{paper.filename}</p>
                          </div>
                        </div>
                      </td>
                      <td className="theme-border max-w-[14rem] border-b px-4 py-4">
                        <span className="theme-text-secondary line-clamp-2 text-xs">{authors || '未识别'}</span>
                      </td>
                      <td className="theme-border w-[22rem] border-b px-4 py-4">
                        <div className="flex items-center justify-between gap-3 text-xs">
                          <span className="theme-text-primary font-semibold">{progressModel.studyProgress}%</span>
                          <span className="theme-text-muted">{getCurrentPageLabel(paper, currentPdfId, currentPage, currentTotalPages)}</span>
                        </div>
                        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200/70">
                          <div className="h-full rounded-full bg-pixiu" style={{ width: `${progressModel.studyProgress}%` }} />
                        </div>
                        <div className="mt-2 flex items-center justify-between gap-3 text-[11px]">
                          <span className="rounded-full bg-pixiu/10 px-2 py-0.5 font-semibold text-pixiu">
                            {progressModel.studyPhase}
                          </span>
                          <span className="theme-text-muted whitespace-nowrap">
                            浅读 {progressModel.axes.survey} · 探究 {progressModel.axes.analysis} · 沉淀 {progressModel.axes.synthesis}
                          </span>
                        </div>
                        <p className="theme-text-muted mt-2 line-clamp-2 text-[11px] leading-5">
                          {progressModel.studySummary}
                        </p>
                      </td>
                      <td className="theme-border border-b px-4 py-4">
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-bold ${statusStyle(status)}`}>
                          {status === '索引异常' ? <AlertCircle size={13} /> : <CheckCircle2 size={13} />}
                          {status}
                        </span>
                      </td>
                      <td className="theme-border border-b px-4 py-4">
                        <span className="theme-text-secondary inline-flex items-center gap-1 text-xs">
                          <Clock3 size={13} />
                          {formatDateTime(paper.timestamp)}
                        </span>
                      </td>
                      <td className="theme-border border-b px-4 py-4">
                        <span className="theme-text-secondary text-xs">{formatDateTime(paper.updatedAt || paper.timestamp)}</span>
                      </td>
                      <td className="theme-border border-b px-5 py-4">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              onSelectPaper(paper.id);
                              onClose();
                            }}
                            className="theme-button-secondary inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs font-semibold"
                          >
                            打开
                            <ArrowRight size={14} />
                          </button>
                          <button
                            type="button"
                            onClick={() => onDeletePaper(paper.id)}
                            className="theme-danger-button rounded-md p-2"
                            title="删除"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </>
  );
};

export default LibrarySidebar;
