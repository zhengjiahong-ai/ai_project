import React, { useEffect } from 'react';
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  Info,
  LayoutDashboard,
  BookOpen,
  Search,
} from 'lucide-react';
import { Group, Panel, Separator } from 'react-resizable-panels';

import BackgroundKnowledgePanel from '../components/BackgroundKnowledgePanel';
import BackgroundReaderProfileEditor from '../components/BackgroundReaderProfileEditor.jsx';
import ChatPanel from '../components/ChatPanel';
import CriticalAnalysisPanel from '../components/CriticalAnalysisPanel';
import DeepResearchPanel from '../components/DeepResearchPanel';
import PaperAnalysis from '../components/PaperAnalysis';
import PdfViewer from '../components/PdfViewer';
import SocraticQuestionsPanel from '../components/SocraticQuestionsPanel';
import TranslationPanel from '../components/TranslationPanel';
import PaperWriterPanel from '../components/PaperWriterPanel.jsx';
import ReadingNotesPanel from '../components/ReadingNotesPanel';
const ReadingStatsPanel = React.lazy(() => import('../components/ReadingStatsPanel.jsx'));
import { ErrorBoundary } from '../components/ErrorBoundary';

import { renderHighlightedText } from '../utils/appHelpers.js';

// Re-exported from App.jsx — imported here to avoid circular-dependency concerns.
const workspaceTabSections = [
  {
    id: 'reading',
    label: '阅读助手',
    description: '围绕当前页面的即时理解与辅助阅读。',
    tabIds: ['chat', 'deconstruct', 'translation'],
  },
  {
    id: 'analysis',
    label: '分析研究',
    description: '偏重批判、补课、引导学习与研究推进。',
    tabIds: ['analysis', 'background', 'socratic', 'deep-research', 'paper-writer'],
  },
  {
    id: 'assets',
    label: '资产沉淀',
    description: '查看当前论文的长期沉淀与工作台入口。',
    tabIds: ['notes', 'stats'],
  },
];

const getWorkspaceSectionId = (tabId) =>
  workspaceTabSections.find((section) => section.tabIds.includes(tabId))?.id || workspaceTabSections[0].id;

const assistantMainTabs = [
  ['chat', '问答'],
  ['deconstruct', '精读'],
  ['translation', '翻译'],
  ['notes', '笔记'],
];

const assistantMoreTabs = [
  ['analysis', '批判分析'],
  ['background', '背景补课'],
  ['socratic', '苏格拉底提问'],
  ['deep-research', '深度研究'],
  ['paper-writer', '论文写作'],
  ['stats', '阅读统计'],
];

export default function ReadingIDE({
  // ── Sidebar ──
  isSidebarCollapsed,
  setIsSidebarCollapsed,
  pdfFile,
  pdfFileName,
  pdfPageState,
  currentPaperStatus,
  readingProgress,
  parseStatus,
  papersList,
  handleSelectPaper,
  setIsLibraryOpen,
  outlineQuery,
  setOutlineQuery,
  currentOutlineItem,
  paperOutlineModel,
  collapsedOutlineIds,
  visibleOutlineItems,
  toggleOutlineCollapse,
  handleSelectOutlineItem,
  isDeconstructing,
  deconstructData,
  setActiveTab,

  // ── PDF Viewer ──
  theme,
  handleExplain,
  addNote,
  pdfHighlights,
  handleHighlightsChange,
  handlePdfPageChange,
  handlePageTextExtracted,
  targetPageIndex,
  targetPageJumpToken,
  focusedSourceRequest,
  pdfId,
  isTranslated,

  // ── Workspace navigation ──
  activeTab,
  activeTabMeta,
  activeWorkspaceSection,
  visibleWorkspaceTabs,
  workspaceTabsRef,
  handleWorkspaceTabsWheel,
  currentWorkflowStage,
  workflowStepSummary,
  setActiveWorkspaceSectionId,
  setIsWorkspaceNavExpanded,
  isWorkspaceNavExpanded,

  // ── Workflow context ──
  readingContext,
  backgroundReaderProfile,
  setBackgroundReaderProfile,
  backgroundReaderProfileSummary,

  // ── Chat panel ──
  messages,
  handleSendMessage,
  handleDeleteChatMessage,
  handleSaveChatToNote,
  handleCaptureChatArtifact,
  handleJumpToSource,
  handleAbortChat,
  isChatLoading,

  // ── Socratic panel ──
  isSocraticLoading,
  socraticSession,
  handleReadingProgressChange,
  handleStartSocratic,
  handleSubmitSocraticAnswer,
  handleRestartSocratic,

  // ── Background knowledge panel ──
  backgroundKnowledgeData,
  isBackgroundKnowledgeLoading,
  handleGenerateBackgroundKnowledge,
  handleCaptureWorkbenchArtifact,

  // ── Deep research panel ──
  currentDeepResearchState,
  currentResearchProgress,
  handleDeepResearchQuestionChange,
  handleStartResearchTask,
  handlePreviewResearchBrief,
  handleDeepResearchBriefConstraintsChange,
  setDeepResearchStateForPdf,
  handleRefreshResearchTask,
  handleCancelResearchTask,
  handleReviewResearchPlan,
  handleReviewResearchFinal,
  fetchDeepResearchTrace,

  // ── Deconstruct panel ──
  paperOutlineItems,

  // ── Critical analysis panel ──
  analysisData,
  handleStartAnalysis,
  isAnalyzing,

  // ── Translation panel ──
  translationState,
  currentTranslationPage,
  handleRetryTranslation,

  // ── Paper writer panel ──
  apiService,

}) {
  // Restore reading progress when a paper is opened
  useEffect(() => {
    if (!pdfId) return;
    let cancelled = false;
    import('../services/highlightStore').then(({ getProgress }) => {
      if (cancelled) return;
      getProgress(pdfId).then((progress) => {
        if (cancelled) return;
        if (progress && progress.pageIndex > 0) {
          const confirmed = window.confirm(
            `恢复上次阅读位置（第 ${progress.pageIndex + 1} 页）？`
          );
          if (confirmed && !cancelled) {
            handleJumpToSource?.({ pageIndex: progress.pageIndex });
          }
        }
      });
    });
    return () => { cancelled = true; };
  }, [pdfId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <aside
        className={`workspace-sidebar theme-panel theme-border hidden shrink-0 flex-col border-r transition-[width] duration-200 lg:flex ${
          isSidebarCollapsed ? 'w-12' : 'w-[292px]'
        }`}
      >
        <div className="workspace-side-title theme-border flex h-16 shrink-0 items-center border-b px-5">
          <div className="flex items-center justify-between gap-2">
            {!isSidebarCollapsed && (
              <h2 className="theme-text-primary text-base font-bold">论文导航</h2>
            )}
            <button
              type="button"
              onClick={() => setIsSidebarCollapsed((value) => !value)}
              className="pixiu-icon-action ml-auto flex h-8 w-8 shrink-0 items-center justify-center"
              title={isSidebarCollapsed ? '展开左侧栏' : '收起左侧栏'}
            >
              {isSidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            </button>
          </div>
        </div>

        <div className={`flex-1 overflow-y-auto ${isSidebarCollapsed ? 'p-2' : 'p-4'}`}>
          {isSidebarCollapsed ? (
            <div className="flex flex-col items-center gap-3">
              <button
                type="button"
                className="theme-button-secondary flex h-9 w-9 items-center justify-center rounded-md"
                title="当前论文"
              >
                <FileText size={16} />
              </button>
              <button
                type="button"
                className="theme-button-secondary flex h-9 w-9 items-center justify-center rounded-md"
                title="篇章目录"
              >
                <LayoutDashboard size={16} />
              </button>
              <button
                type="button"
                onClick={() => setIsLibraryOpen(true)}
                className="theme-button-secondary flex h-9 w-9 items-center justify-center rounded-md"
                title="论文库"
              >
                <BookOpen size={16} />
              </button>
            </div>
          ) : (
            <>
              <section className="mb-5">
                <div className="theme-text-muted mb-2 flex items-center justify-between text-xs font-bold">
                  <span>当前论文</span>
                  <span>{currentPaperStatus} · {readingProgress}%</span>
                </div>
                <div className="theme-card-soft rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    <FileText size={16} className="mt-0.5 shrink-0 text-pixiu" />
                    <div className="min-w-0">
                      <p className="theme-text-primary line-clamp-2 text-sm font-semibold">
                        {pdfFileName || '尚未上传论文'}
                      </p>
                      {!pdfFile && <p className="theme-text-muted mt-1 text-xs">请上传 PDF</p>}
                    </div>
                  </div>
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200/70">
                    <div
                      className="h-full rounded-full bg-pixiu"
                      style={{ width: `${readingProgress}%` }}
                    />
                  </div>
                </div>
              </section>

              <section className="mb-5">
                <div className="mb-2 flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="theme-text-muted text-xs font-bold">篇章目录</div>
                    {currentOutlineItem && (
                      <div className="theme-text-muted mt-0.5 truncate text-[10px]">
                        当前：{currentOutlineItem.label}
                      </div>
                    )}
                  </div>
                  <span className={`outline-source-badge outline-source-badge-${paperOutlineModel.source}`}>
                    {paperOutlineModel.sourceLabel}
                  </span>
                </div>

                <label className="theme-input mb-2 flex items-center gap-2 rounded-md px-2 py-1.5 text-xs">
                  <Search size={13} className="theme-text-muted shrink-0" />
                  <input
                    value={outlineQuery}
                    onChange={(event) => setOutlineQuery(event.target.value)}
                    className="theme-text-primary min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-slate-400"
                    placeholder="搜索标题、页码或摘要"
                    aria-label="搜索篇章目录"
                  />
                </label>

                <div className="outline-tree text-xs">
                  {visibleOutlineItems.map((item) => {
                    const isCollapsed = Boolean(collapsedOutlineIds[item.id]);
                    const isCurrent = currentOutlineItem?.id === item.id;
                    const isCurrentPath = currentOutlineItem?.ancestorIds?.includes(item.id);

                    return (
                      <div
                        key={item.id}
                        className="outline-tree-row"
                        style={{ paddingLeft: `${(item.level - 1) * 12}px` }}
                      >
                        {item.hasChildren ? (
                          <button
                            type="button"
                            className="outline-collapse-toggle"
                            onClick={() => toggleOutlineCollapse(item.id)}
                            aria-label={isCollapsed ? '展开子章节' : '收起子章节'}
                            aria-expanded={!isCollapsed || Boolean(outlineQuery)}
                          >
                            {isCollapsed && !outlineQuery ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                          </button>
                        ) : (
                          <span className="outline-collapse-spacer" />
                        )}

                        <button
                          type="button"
                          className={`outline-tree-item ${
                            isCurrent ? 'outline-tree-item-current' : ''
                          } ${isCurrentPath ? 'outline-tree-item-path' : ''}`}
                          onClick={() => handleSelectOutlineItem(item)}
                          title={[
                            item.label,
                            item.sourceLabel ? `来源：${item.sourceLabel}` : '',
                            Number.isFinite(item.confidence) ? `置信度：${Math.round(item.confidence * 100)}%` : '',
                            item.preview,
                          ].filter(Boolean).join('\n')}
                          aria-current={isCurrent ? 'true' : undefined}
                        >
                          <span className="min-w-0 flex-1 truncate">
                            {renderHighlightedText(item.label, outlineQuery)}
                          </span>
                          <span className="outline-page-label">
                            {item.pageLabel || item.meta}
                          </span>
                        </button>
                      </div>
                    );
                  })}

                  {paperOutlineItems.length > 0 && visibleOutlineItems.length === 0 && (
                    <div className="theme-empty-state rounded-md px-3 py-2 text-center text-xs">
                      没有匹配的篇章
                    </div>
                  )}

                  {paperOutlineItems.length === 0 && (
                    <div className="theme-empty-state rounded-md px-3 py-3 text-center text-xs">
                      <p>
                        {isDeconstructing
                          ? '正在解析论文结构...'
                          : deconstructData
                            ? '未能识别可导航的论文结构'
                            : '上传论文后显示真实论文结构'}
                      </p>
                      {!isDeconstructing && (
                        <button
                          type="button"
                          onClick={() => setActiveTab('deconstruct')}
                          className="mt-2 text-[11px] font-semibold text-pixiu"
                        >
                          篇章解构
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </section>

              <section>
                <div className="theme-text-muted mb-2 flex items-center justify-between text-xs font-bold">
                  <span>最近论文</span>
                  <button type="button" onClick={() => setIsLibraryOpen(true)} className="text-pixiu">
                    全部
                  </button>
                </div>
                <div className="space-y-2">
                  {papersList.slice(0, 4).map((paper) => (
                    <button
                      key={paper.id}
                      type="button"
                      onClick={() => handleSelectPaper(paper.id)}
                      className={`theme-border w-full rounded-lg border p-2 text-left transition hover:border-pixiu/40 ${
                        paper.id === pdfId ? 'bg-pixiu/10' : 'theme-panel'
                      }`}
                    >
                      <span className="theme-text-primary line-clamp-2 text-xs font-semibold">{paper.filename}</span>
                      <span className="theme-text-muted mt-1 block text-[10px]">
                        {new Date(paper.timestamp).toLocaleDateString()}
                      </span>
                    </button>
                  ))}
                  {papersList.length === 0 && (
                    <div className="theme-empty-state rounded-lg p-3 text-center text-xs">论文库暂无内容</div>
                  )}
                </div>
              </section>
            </>
          )}
        </div>
      </aside>

      <section className="min-w-0 flex-1 overflow-hidden" aria-label="PDF阅读区">
        <Group orientation="horizontal">
              <Panel defaultSize={58} minSize={34}>
                <ErrorBoundary area="PDF阅读区">
                  <div className="pdf-stage relative flex h-full flex-col p-3">
                    <div className="workspace-pdf-header theme-panel theme-border mb-2 flex h-10 shrink-0 items-center justify-between rounded-md border px-3 text-sm">
                      <div className="flex min-w-0 items-center gap-2">
                        <FileText size={16} className="text-pixiu" />
                        <span className="theme-text-primary truncate font-medium">
                          {pdfFileName || '上传论文后在此阅读 PDF'}
                        </span>
                      </div>
                      <div className="theme-text-muted hidden items-center gap-3 text-xs md:flex">
                        <span>
                          第 {pdfFile ? pdfPageState.pageIndex + 1 : 0} / {pdfPageState.totalPages || 0} 页
                        </span>
                        <span>阅读 {readingProgress}%</span>
                        <span>划词解释</span>
                        {isTranslated && <span className="text-pixiu">译文已开启</span>}
                      </div>
                    </div>

                    <div className="pdf-viewer-shell flex-1 overflow-hidden rounded-md">
                      <PdfViewer
                        fileUrl={pdfFile}
                        pdfId={pdfId}
                        paperSkeleton={deconstructData?.paper_skeleton || null}
                        theme={theme}
                        translationLayoutIndex={deconstructData?.translationLayoutIndex || {}}
                        onSelection={handleExplain}
                        onSaveNote={addNote}
                        initialHighlights={pdfHighlights}
                        onHighlightsChange={handleHighlightsChange}
                        onPageChange={handlePdfPageChange}
                        onPageTextExtracted={handlePageTextExtracted}
                        targetPageIndex={targetPageIndex}
                        targetPageJumpToken={targetPageJumpToken}
                        focusedSourceAnchorId={focusedSourceRequest.anchorId}
                        focusedSourceAnchorToken={focusedSourceRequest.token}
                        parseStatus={parseStatus}
                        onNarrowScreenChange={setIsSidebarCollapsed}
                      />
                    </div>
                  </div>
                </ErrorBoundary>
              </Panel>

              <Separator className="group relative w-1.5 transition-all hover:bg-pixiu/10">
                <div className="app-separator-line absolute inset-y-0 left-1/2 w-[2px] -translate-x-1/2 transition-colors group-hover:bg-pixiu/40" />
              </Separator>

              <Panel defaultSize={42} minSize={32}>
                <ErrorBoundary area="功能面板区">
                  <div className="panel-shell flex h-full flex-col">
                    <div className="reading-assistant-nav theme-panel theme-border shrink-0 border-b">
                      <div className="flex h-12 items-center px-5">
                        <h2 className="theme-text-primary text-base font-bold">阅读助手</h2>
                      </div>
                      <div className="flex h-10 items-end gap-1 px-4">
                        {assistantMainTabs.map(([tabId, label]) => (
                          <button
                            key={tabId}
                            type="button"
                            onClick={() => {
                              setActiveWorkspaceSectionId(getWorkspaceSectionId(tabId));
                              setActiveTab(tabId);
                            }}
                            className={`reading-assistant-tab shrink-0 ${activeTab === tabId ? 'reading-assistant-tab-active' : ''}`}
                          >
                            {label}
                          </button>
                        ))}
                        <details className="relative shrink-0">
                          <summary
                            className={`reading-assistant-tab reading-assistant-more flex cursor-pointer list-none items-center gap-1 ${
                              assistantMoreTabs.some(([id]) => id === activeTab) ? 'reading-assistant-tab-active' : ''
                            }`}
                          >
                            更多工具
                            <ChevronDown size={12} />
                          </summary>
                          <div className="theme-card absolute left-0 top-full z-30 mt-1 w-40 rounded-md p-1.5 shadow-lg">
                            {assistantMoreTabs.map(([tabId, label]) => (
                              <button
                                key={tabId}
                                type="button"
                                onClick={() => {
                                  setActiveWorkspaceSectionId(getWorkspaceSectionId(tabId));
                                  setActiveTab(tabId);
                                }}
                                className={`w-full rounded px-3 py-2 text-left text-xs ${
                                  activeTab === tabId
                                    ? 'bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)]'
                                    : 'theme-text-secondary hover:bg-[color:var(--panel-muted)]'
                                }`}
                              >
                                {label}
                              </button>
                            ))}
                          </div>
                        </details>
                      </div>
                    </div>
                    <div className="theme-panel theme-border hidden shrink-0 flex-col border-b">
                      <div className="workspace-top-panels">
                        <div className="workspace-top-panels-collapsed">
                          <div className="flex min-w-0 items-center gap-2">
                            <Info size={16} className="text-pixiu" />
                            <div className="min-w-0">
                              <h2 className="theme-text-primary truncate text-sm font-bold">辅助导航</h2>
                              <div className="theme-text-muted truncate text-[11px]">
                                {activeTabMeta.label} · {currentWorkflowStage.label}
                              </div>
                            </div>
                          </div>
                          <div className="workspace-top-panels-status">
                            {currentDeepResearchState.task ? `研究 ${currentResearchProgress}%` : `${visibleWorkspaceTabs.length} 项功能`}
                          </div>
                        </div>

                        <div className="workspace-top-panels-expanded">
                          <div className="px-3 pb-2">
                            <div className="workflow-stage-strip flex gap-2 overflow-x-auto">
                              {workflowStepSummary.map((stage) => {
                                const isActiveStage = stage.id === currentWorkflowStage.id;
                                return (
                                  <button
                                    key={stage.id}
                                    type="button"
                                    onClick={() => {
                                      const targetTabId = stage.tabIds[0];
                                      setActiveWorkspaceSectionId(getWorkspaceSectionId(targetTabId));
                                      setActiveTab(targetTabId);
                                    }}
                                    className={`workflow-stage-chip ${stage.status} ${
                                      isActiveStage ? 'workflow-stage-chip-active' : ''
                                    }`}
                                    title={stage.description}
                                  >
                                    <span className="workflow-stage-chip-label">{stage.shortLabel}</span>
                                    <span className="workflow-stage-chip-title">{stage.label}</span>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                          <div className="workspace-top-summary-grid px-3 pb-2">
                            <div className="workflow-context-card theme-card-soft rounded-xl p-3">
                              <div className="flex items-center justify-between gap-2">
                                <div className="theme-text-primary text-xs font-semibold">当前研读上下文</div>
                                <span className="theme-text-muted text-[10px]">{readingContext.artifactCount} 条已沉淀</span>
                              </div>
                              <div className="mt-2 grid gap-1 text-[11px] leading-5 theme-text-secondary">
                                <div className="flex gap-2">
                                  <span className="workflow-context-label">章节</span>
                                  <span className="truncate">{readingContext.sectionTitle}</span>
                                </div>
                                <div className="flex gap-2">
                                  <span className="workflow-context-label">位置</span>
                                  <span>{readingContext.pageLabel}</span>
                                </div>
                                {readingContext.sourceSnippet && (
                                  <div className="flex gap-2">
                                    <span className="workflow-context-label">原文</span>
                                    <span className="min-w-0 flex-1 truncate">{readingContext.sourceSnippet}</span>
                                  </div>
                                )}
                                {readingContext.latestQuestion && (
                                  <div className="flex gap-2">
                                    <span className="workflow-context-label">问题</span>
                                    <span className="min-w-0 flex-1 truncate">{readingContext.latestQuestion}</span>
                                  </div>
                                )}
                              </div>
                            </div>
                            <div className="workflow-profile-card theme-card rounded-xl p-3">
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="theme-text-primary text-xs font-semibold">背景补课偏好</div>
                                  <div className="theme-text-secondary mt-1 text-[11px] leading-5">
                                    这里决定补课的深浅、目标和当前卡点，生成背景补课时会直接作为上下文透传。
                                  </div>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setActiveWorkspaceSectionId(getWorkspaceSectionId('background'));
                                    setActiveTab('background');
                                  }}
                                  className="workflow-next-action"
                                >
                                  去补课
                                </button>
                              </div>
                              <div className="mt-3">
                                <BackgroundReaderProfileEditor
                                  value={backgroundReaderProfile}
                                  onChange={setBackgroundReaderProfile}
                                  compact
                                />
                              </div>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {backgroundReaderProfileSummary.map((item) => (
                                  <span key={item} className="workbench-kind-chip">
                                    {item}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>
                          <div className="px-3 pb-2">
                            <button
                              type="button"
                              onClick={() => setIsWorkspaceNavExpanded((current) => !current)}
                              className={`workspace-nav-toggle ${isWorkspaceNavExpanded ? 'workspace-nav-toggle-active' : ''}`}
                              title={isWorkspaceNavExpanded ? '收起功能导航' : '展开功能导航'}
                            >
                              <span>功能导航</span>
                              <span className="workspace-nav-toggle-meta">
                                {visibleWorkspaceTabs.length} 项
                              </span>
                              <ChevronDown
                                size={14}
                                className={`transition-transform ${isWorkspaceNavExpanded ? 'rotate-180' : ''}`}
                              />
                            </button>
                          </div>
                          {isWorkspaceNavExpanded && (
                            <>
                              <div className="workspace-section-tabs flex flex-wrap gap-2 px-3 pb-2">
                                {workspaceTabSections.map((section) => {
                                  const isActiveSection = section.id === activeWorkspaceSection.id;
                                  return (
                                    <button
                                      key={section.id}
                                      type="button"
                                      onClick={() => {
                                        setActiveWorkspaceSectionId(section.id);
                                        if (!section.tabIds.includes(activeTab)) {
                                          setActiveTab(section.tabIds[0]);
                                        }
                                      }}
                                      className={`workspace-section-tab ${
                                        isActiveSection ? 'workspace-section-tab-active' : ''
                                      }`}
                                      title={section.description}
                                    >
                                      {section.label}
                                    </button>
                                  );
                                })}
                              </div>
                              <div
                                ref={workspaceTabsRef}
                                className="workspace-tabs flex gap-1 overflow-x-auto px-2 pb-2"
                                onWheel={handleWorkspaceTabsWheel}
                                title="鼠标悬停后滚轮可横向切换功能标签"
                              >
                                {visibleWorkspaceTabs.map((item) => {
                                  const Icon = item.icon;
                                  const isActive = activeTab === item.id;
                                  return (
                                    <button
                                      key={item.id}
                                      type="button"
                                      data-active-tab={isActive ? 'true' : undefined}
                                      onClick={() => setActiveTab(item.id)}
                                      className={`workspace-tab-button flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold transition ${
                                        isActive ? 'workspace-tab-button-active' : ''
                                      }`}
                                    >
                                      <Icon size={14} />
                                      {item.label}
                                    </button>
                                  );
                                })}
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="min-h-0 flex-1 overflow-hidden">
                      {activeTab === 'chat' && (
                        <ChatPanel
                          messages={messages}
                          onSendMessage={handleSendMessage}
                          onDeleteMessage={handleDeleteChatMessage}
                          onSaveToNote={handleSaveChatToNote}
                          onCaptureArtifact={handleCaptureChatArtifact}
                          onJumpToSource={handleJumpToSource}
                          onAbortChat={() => handleAbortChat(pdfId)}
                          isLoading={isChatLoading(pdfId)}
                          contextLabel={[readingContext.pageLabel, readingContext.sectionTitle].filter(Boolean).join(' · ')}
                        />
                      )}

                      {activeTab === 'socratic' && (
                        <SocraticQuestionsPanel
                          hasPaperContext={!!deconstructData?.paper_skeleton}
                          isLoading={isSocraticLoading}
                          session={socraticSession}
                          onReadingProgressChange={handleReadingProgressChange}
                          onStart={handleStartSocratic}
                          onSubmitAnswer={handleSubmitSocraticAnswer}
                          onRestart={handleRestartSocratic}
                        />
                      )}

                      {activeTab === 'background' && (
                        <BackgroundKnowledgePanel
                          data={backgroundKnowledgeData}
                          isLoading={isBackgroundKnowledgeLoading}
                          hasPaperContext={!!deconstructData?.paper_skeleton}
                          onGenerate={handleGenerateBackgroundKnowledge}
                          readerProfile={backgroundReaderProfile}
                          onCaptureArtifact={handleCaptureWorkbenchArtifact}
                          onJumpToSource={handleJumpToSource}
                        />
                      )}

                      {activeTab === 'deep-research' && (
                        <DeepResearchPanel
                          pdfFileName={pdfFileName}
                          paperStructure={deconstructData?.paper_structure || null}
                          questionDraft={currentDeepResearchState.questionDraft}
                          task={currentDeepResearchState.task}
                          errorMessage={currentDeepResearchState.errorMessage}
                          pollError={currentDeepResearchState.pollError}
                          isCreating={currentDeepResearchState.isCreating}
                          isCancelling={currentDeepResearchState.isCancelling}
                          briefPreview={currentDeepResearchState.briefPreview}
                          briefConstraintsDraft={currentDeepResearchState.briefConstraintsDraft}
                          isPreviewingBrief={currentDeepResearchState.isPreviewingBrief}
                          briefError={currentDeepResearchState.briefError}
                          traceSummary={currentDeepResearchState.traceSummary}
                          traceError={currentDeepResearchState.traceError}
                          isTraceLoading={currentDeepResearchState.isTraceLoading}
                          isTracePanelEnabled={Boolean(import.meta.env?.DEV)}
                          allowExternalSearch={Boolean(currentDeepResearchState.allowExternalSearch)}
                          onQuestionChange={handleDeepResearchQuestionChange}
                          onStart={handleStartResearchTask}
                          onPreviewBrief={handlePreviewResearchBrief}
                          onBriefConstraintsChange={handleDeepResearchBriefConstraintsChange}
                          onAcceptBrief={() => handleStartResearchTask({ useBriefPreview: true })}
                          onAllowExternalSearchChange={(value) => setDeepResearchStateForPdf(pdfId, (prev) => ({ ...prev, allowExternalSearch: Boolean(value) }))}
                          onRefresh={handleRefreshResearchTask}
                          onCancel={handleCancelResearchTask}
                          onReviewPlan={handleReviewResearchPlan}
                          onReviewFinal={handleReviewResearchFinal}
                          onRefreshTrace={() => fetchDeepResearchTrace(pdfId, currentDeepResearchState.task?.traceId)}
                          onCaptureArtifact={handleCaptureWorkbenchArtifact}
                          onJumpToSource={handleJumpToSource}
                        />
                      )}

                      {activeTab === 'deconstruct' && (
                        <PaperAnalysis
                          data={deconstructData}
                          isLoading={isDeconstructing}
                          outlineItems={paperOutlineItems}
                          pdfId={pdfId}
                          onSelectOutlineItem={handleSelectOutlineItem}
                          onCaptureArtifact={handleCaptureWorkbenchArtifact}
                        />
                      )}

                      {activeTab === 'analysis' && (
                        <CriticalAnalysisPanel
                          data={analysisData}
                          onAnalyze={handleStartAnalysis}
                          isLoading={isAnalyzing}
                          onCaptureArtifact={handleCaptureWorkbenchArtifact}
                          onJumpToSource={handleJumpToSource}
                        />
                      )}

                      {activeTab === 'translation' && (
                        <TranslationPanel
                          pdfId={pdfId}
                          pdfFileName={pdfFileName}
                          currentPage={translationState.currentPage}
                          pageData={currentTranslationPage}
                          onRetry={handleRetryTranslation}
                          onCaptureArtifact={handleCaptureWorkbenchArtifact}
                        />
                      )}

                      {activeTab === 'paper-writer' && (
                        <PaperWriterPanel
                          apiService={apiService}
                          onSaveToWorkbench={handleCaptureWorkbenchArtifact}
                        />
                      )}

                      {activeTab === 'notes' && (
                        <ReadingNotesPanel
                          pdfId={pdfId}
                          paperSkeleton={deconstructData?.paper_skeleton || null}
                          currentPageIndex={pdfPageState?.pageIndex ?? 0}
                          onJumpToPage={(pageIndex) => {
                            handleJumpToSource?.({ pageIndex });
                          }}
                          theme={theme}
                        />
                      )}

                      {activeTab === 'stats' && (
                        <ReadingStatsPanel
                          pdfId={pdfId}
                          isDark={theme === 'dark'}
                        />
                      )}
                    </div>
                  </div>
                </ErrorBoundary>
          </Panel>
        </Group>
      </section>
    </>
  );
}
