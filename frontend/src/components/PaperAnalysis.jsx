import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileText,
  LayoutDashboard,
  Loader2,
  MessageSquare,
  MousePointer2,
  Network,
} from 'lucide-react';

import InsightCard from './InsightCard';
import { buildDeconstructionArtifact } from './artifactModel.ts';
import { getParseWarningMessage } from './parseStatusModel.js';

const outlineSourceLabels = {
  tei: 'PDF结构',
  layout: '版面补全',
  'pdf-layout': 'PDF行补全',
  'tei+layout': 'PDF+版面',
  inferred: '推断结构',
  pdf: 'PDF结构',
};

const sectionLabels = {
  abstract: '摘要',
  introduction: '引言',
  methods: '方法',
  results: '结果',
  discussion: '讨论',
  conclusion: '结论',
};

const readingModes = [
  {
    id: 'overview',
    label: '先看全局',
    description: '先判断这篇论文值不值得继续深读。',
  },
  {
    id: 'outline',
    label: '再看目录',
    description: '顺着目录决定接下来精读哪里。',
  },
  {
    id: 'sections',
    label: '最后进细节',
    description: '按章节逐步展开，而不是一次看完所有骨架。',
  },
];

const PaperAnalysis = ({ data, isLoading, outlineItems = [], pdfId, onSelectOutlineItem, onCaptureArtifact }) => {
  const [activeMode, setActiveMode] = useState('overview');
  const [visibleSectionCount, setVisibleSectionCount] = useState(2);
  const parseWarning = getParseWarningMessage(data);

  const availableSections = useMemo(
    () =>
      Object.entries(sectionLabels)
        .map(([key, label]) => ({
          key,
          label,
          content: data?.paper_skeleton?.[key],
        }))
        .filter((section) => !parseWarning && section.content && !section.content.includes('请提供具体内容')),
    [data?.paper_skeleton, parseWarning],
  );

  const overviewSummary = useMemo(() => {
    if (availableSections.length === 0) {
      return null;
    }

    return {
      summary: `系统已经整理出 ${availableSections.length} 个核心章节。建议先看摘要与结论，再决定是否深入方法和实验。`,
      keyPoints: [
        outlineItems.length > 0 ? `已识别 ${outlineItems.length} 个可导航章节` : '目录仍在补全中',
        availableSections.slice(0, 3).map((section) => section.label).join(' / '),
        data?.paper_structure?.outlineVersion ? `目录版本 ${data.paper_structure.outlineVersion}` : '使用默认目录识别策略',
      ],
    };
  }, [availableSections, data, outlineItems.length]);

  const quickActions = [
    {
      label: '进入问答',
      icon: MessageSquare,
      hint: '先问一个最想弄明白的问题。',
    },
    {
      label: '继续批判阅读',
      icon: Network,
      hint: '把结构理解推进到论证判断。',
    },
    {
      label: '跳到原文',
      icon: ArrowRight,
      hint: '从目录直接进入 PDF 对应位置。',
    },
  ];
  const captureSection = (section) => {
    const artifact = buildDeconstructionArtifact({
      pdfId,
      sectionId: section.key,
      sectionLabel: section.label,
      content: section.content,
    });
    if (artifact) onCaptureArtifact?.(artifact);
  };

  const renderSectionCapture = (section) => (
    <button
      type="button"
      onClick={() => captureSection(section)}
      disabled={!pdfId || !onCaptureArtifact}
      title={!pdfId ? '请先打开一篇论文。' : `保存${section.label}摘要`}
      className="source-link-chip disabled:cursor-not-allowed disabled:opacity-50"
    >
      加入工作台
    </button>
  );

  if (isLoading) {
    return (
      <div className="theme-empty-state flex h-full flex-col items-center justify-center p-8 font-medium">
        <Loader2 className="mb-4 animate-spin text-pixiu" size={40} />
        <p className="text-sm font-medium">正在生成论文骨架，先给你一个可浏览的结构，再逐步补齐章节内容。</p>
      </div>
    );
  }

  if (!data || (!data.paper_skeleton && !data.paper_structure)) {
    return (
      <div className="theme-empty-state flex h-full flex-col items-center justify-center p-8">
        <FileText size={48} className="mb-4 opacity-20" />
        <p>先上传一篇 PDF，系统会把篇章结构整理成可进入阅读的起点。</p>
      </div>
    );
  }

  const visibleSections = availableSections.slice(0, visibleSectionCount);
  const hasMoreSections = visibleSectionCount < availableSections.length;

  return (
    <div className="theme-panel-muted flex h-full flex-col overflow-hidden">
      <div className="theme-panel theme-border sticky top-0 z-10 border-b px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <LayoutDashboard size={18} className="text-pixiu" />
              <h2 className="theme-text-primary text-lg font-bold">篇章解构</h2>
            </div>
            <p className="theme-text-secondary mt-1 text-xs">把后端给出的骨架拆成三步：先看结论，再看目录，最后按需展开章节。</p>
          </div>
          <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${parseWarning ? 'bg-amber-500/10 text-amber-600' : 'bg-emerald-500/10 text-emerald-500'}`}>
            {parseWarning ? '需 OCR' : '已解构'}
          </span>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {readingModes.map((mode) => (
            <button
              key={mode.id}
              type="button"
              onClick={() => setActiveMode(mode.id)}
              className={`workspace-section-tab ${activeMode === mode.id ? 'workspace-section-tab-active' : ''}`}
              title={mode.description}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        {parseWarning && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-amber-700">
            <div className="flex items-start gap-3">
              <AlertTriangle size={18} className="mt-0.5 shrink-0" />
              <div>
                <h3 className="text-sm font-bold">当前 PDF 需要 OCR</h3>
                <p className="mt-1 text-xs leading-6">{parseWarning}</p>
              </div>
            </div>
          </div>
        )}
        {overviewSummary && (
          <InsightCard
            title="这篇论文先看什么"
            icon={<LayoutDashboard size={16} className="text-pixiu" />}
            summary={overviewSummary.summary}
            keyPoints={overviewSummary.keyPoints}
            detailsTitle="展开总览说明"
            footer={
              <div className="flex flex-wrap gap-2">
                {quickActions.map((action) => {
                  const Icon = action.icon;
                  return (
                    <span key={action.label} className="source-link-chip inline-flex items-center gap-1" title={action.hint}>
                      <Icon size={12} />
                      {action.label}
                    </span>
                  );
                })}
              </div>
            }
          />
        )}

        {activeMode === 'overview' && (
          <div className="grid gap-4 md:grid-cols-2">
            {availableSections
              .filter((section) => ['abstract', 'conclusion'].includes(section.key))
              .map((section) => (
                <InsightCard
                  key={section.key}
                  title={`先读 ${section.label}`}
                  icon={<CheckCircle2 size={14} className="text-pixiu" />}
                  content={section.content}
                  detailsTitle={`展开 ${section.label}`}
                  defaultExpanded={section.key === 'abstract'}
                  footer={renderSectionCapture(section)}
                />
              ))}

            {outlineItems.length > 0 && (
              <div className="theme-card rounded-2xl p-5">
                <div className="theme-text-primary mb-2 text-sm font-bold">快速目录入口</div>
                <div className="theme-text-secondary mb-4 text-xs leading-6">
                  你不用一次看完整个目录，先从最靠前的几个主章节里挑一个进入原文。
                </div>
                <div className="space-y-2">
                  {outlineItems.slice(0, 5).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => onSelectOutlineItem?.(item)}
                      className="theme-button-secondary flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left"
                    >
                      <MousePointer2 size={12} className="shrink-0 text-pixiu" />
                      <span className="theme-text-primary min-w-0 flex-1 truncate text-sm font-semibold">{item.label}</span>
                      <span className="theme-text-muted shrink-0 text-xs">{item.pageLabel || item.meta}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeMode === 'outline' && (
          <section className="theme-card rounded-2xl p-5">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h3 className="theme-text-primary flex items-center gap-2 text-sm font-bold">
                  <LayoutDashboard size={16} className="text-pixiu" />
                  可导航章节
                </h3>
                <p className="theme-text-muted mt-1 text-xs">
                  这里建议你先点一两个最关键章节，而不是把目录从头滚到尾。
                </p>
              </div>
              <span className="rounded-full bg-pixiu/10 px-2 py-0.5 text-[10px] font-bold text-pixiu">
                {outlineItems.length} 项
              </span>
            </div>

            <div className="space-y-2">
              {outlineItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelectOutlineItem?.(item)}
                  className="theme-button-secondary flex w-full items-center gap-2 rounded-md px-2 py-2 text-left transition"
                  style={{ paddingLeft: `${10 + (item.level - 1) * 14}px` }}
                  title={item.preview ? `${item.label}\n${item.preview}` : item.label}
                >
                  <MousePointer2 size={12} className="shrink-0 text-pixiu" />
                  <span className="theme-text-primary min-w-0 flex-1 truncate font-semibold">{item.label}</span>
                  <span className="theme-text-muted shrink-0 text-xs">{item.pageLabel || item.meta}</span>
                  <span className="shrink-0 rounded-full bg-slate-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
                    {outlineSourceLabels[item.source] || item.sourceLabel || '结构'}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {activeMode === 'sections' && (
          <section className="space-y-4">
            {visibleSections.map((section) => (
              <InsightCard
                key={section.key}
                title={section.label}
                icon={<CheckCircle2 size={14} className="text-pixiu" />}
                content={section.content}
                detailsTitle={`展开 ${section.label}`}
                defaultExpanded={section.key === 'abstract'}
                footer={renderSectionCapture(section)}
              />
            ))}

            {hasMoreSections && (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={() => setVisibleSectionCount((count) => Math.min(count + 2, availableSections.length))}
                  className="workflow-next-action workflow-next-action-primary"
                >
                  再展开 2 个章节
                </button>
              </div>
            )}
          </section>
        )}

        <p className="theme-text-muted pb-4 text-center text-[10px]">以上内容由 AI 自动生成，建议结合原文核对。</p>
      </div>
    </div>
  );
};

export default PaperAnalysis;
