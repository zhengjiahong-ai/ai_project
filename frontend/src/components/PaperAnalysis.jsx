import React, { useMemo } from 'react';
import { CheckCircle2, FileText, LayoutDashboard, Loader2, MousePointer2 } from 'lucide-react';
import InsightCard from './InsightCard.jsx';

const outlineSourceLabels = {
  tei: 'PDF结构',
  layout: '版面补全',
  'pdf-layout': 'PDF行补全',
  'tei+layout': 'PDF+版面',
  inferred: '推断结构',
  pdf: 'PDF结构',
};

const LATEST_OUTLINE_VERSION = '1.4';

const PaperAnalysis = ({
  data,
  isLoading,
  outlineItems = [],
  onSelectOutlineItem,
}) => {
  if (isLoading) {
    return (
      <div className="theme-empty-state flex h-full flex-col items-center justify-center p-8 font-medium">
        <Loader2 className="mb-4 animate-spin text-pixiu" size={40} />
        <p className="text-sm font-medium">大模型正在解构论文，请稍候（约 15-30s）...</p>
      </div>
    );
  }

  if (!data || (!data.paper_skeleton && !data.paper_structure)) {
    return (
      <div className="theme-empty-state flex h-full flex-col items-center justify-center p-8">
        <FileText size={48} className="mb-4 opacity-20" />
        <p>请先在导航栏上传 PDF 论文以生成深度解构报告。</p>
      </div>
    );
  }

  const sectionLabels = {
    abstract: '摘要 (Abstract)',
    introduction: '引言 (Introduction)',
    methods: '方法 (Methods)',
    results: '结果 (Results)',
    discussion: '讨论 (Discussion)',
    conclusion: '结论 (Conclusion)',
  };
  const outlineVersion = data.paper_structure?.outlineVersion || '';
  const isLegacyOutline = outlineVersion && outlineVersion !== LATEST_OUTLINE_VERSION;
  const layoutRecoveredCount = outlineItems.filter((item) => item.source === 'layout').length;
  const pdfLineRecoveredCount = outlineItems.filter((item) => item.source === 'pdf-layout').length;
  const mergedSourceCount = outlineItems.filter((item) => item.source === 'tei+layout').length;
  const overviewSummary = useMemo(() => {
    const availableSections = Object.entries(sectionLabels)
      .map(([key, label]) => ({
        key,
        label,
        content: data.paper_skeleton?.[key],
      }))
      .filter((section) => section.content && !section.content.includes('请提供具体内容'));

    if (availableSections.length === 0) {
      return null;
    }

    return {
      summary: `${availableSections.length} 个核心章节已经完成结构化解构，可先浏览整体轮廓，再按章节展开细读。`,
      keyPoints: [
        outlineItems.length > 0 ? `已识别 ${outlineItems.length} 个可导航章节` : '尚未生成可导航目录',
        outlineVersion ? `当前目录规则版本：${outlineVersion}` : '当前使用默认目录识别',
        availableSections.slice(0, 3).map((section) => section.label).join('、'),
      ],
    };
  }, [data.paper_skeleton, outlineItems.length, outlineVersion]);

  return (
    <div className="theme-panel-muted flex h-full flex-col overflow-hidden">
      <div className="theme-panel theme-border sticky top-0 z-10 flex items-center justify-between border-b px-6 py-4">
        <div className="rounded-2xl border border-pixiu/10 bg-pixiu/5 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-pixiu text-white shadow-lg">
              <LayoutDashboard size={20} />
            </div>
            <div>
              <h2 className="theme-text-primary text-xl font-bold">篇章逻辑解构</h2>
              <p className="theme-text-secondary text-xs font-medium">深度拆解论文架构，洞察核心逻辑点</p>
            </div>
          </div>
        </div>
        <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-500">
          AI 已完成
        </span>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        {overviewSummary && (
          <InsightCard
            title="结构总览"
            icon={<LayoutDashboard size={16} className="text-pixiu" />}
            summary={overviewSummary.summary}
            keyPoints={overviewSummary.keyPoints}
          />
        )}

        {outlineItems.length > 0 && (
          <section className="theme-card rounded-2xl p-5 transition hover:shadow-md">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h3 className="theme-text-primary flex items-center gap-2 text-sm font-bold">
                  <LayoutDashboard size={16} className="text-pixiu" />
                  真实篇章结构
                </h3>
                <p className="theme-text-muted mt-1 text-xs">
                  基于 PDF 结构与版面补全生成，共 {outlineItems.length} 个节点
                  {outlineVersion ? ` · 结构版本 ${outlineVersion}` : ''}
                </p>
                {isLegacyOutline && (
                  <p className="mt-1 text-[11px] font-semibold text-amber-600">
                    当前结构由旧规则生成，重新上传或重新解析后可使用 {LATEST_OUTLINE_VERSION} 目录补全规则。
                  </p>
                )}
              </div>
              {(layoutRecoveredCount > 0 || pdfLineRecoveredCount > 0 || mergedSourceCount > 0) && (
                <span className="rounded-full bg-pixiu/10 px-2 py-0.5 text-[10px] font-bold text-pixiu">
                  补全 {layoutRecoveredCount + pdfLineRecoveredCount + mergedSourceCount}
                </span>
              )}
            </div>

            <div className="max-h-72 space-y-1 overflow-y-auto pr-1 text-xs">
              {outlineItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelectOutlineItem?.(item)}
                  className="theme-button-secondary flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition"
                  style={{ paddingLeft: `${8 + (item.level - 1) * 14}px` }}
                  title={item.preview ? `${item.label}\n${item.preview}` : item.label}
                >
                  <MousePointer2 size={12} className="shrink-0 text-pixiu" />
                  <span className="theme-text-primary min-w-0 flex-1 truncate font-semibold">
                    {item.label}
                  </span>
                  <span className="theme-text-muted shrink-0">
                    {item.pageLabel || item.meta}
                  </span>
                  <span className="shrink-0 rounded-full bg-slate-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
                    {outlineSourceLabels[item.source] || item.sourceLabel || '结构'}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {Object.entries(sectionLabels).map(([key, label]) => {
          const content = data.paper_skeleton?.[key];
          if (!content || content.includes('请提供具体内容')) return null;

          return (
            <InsightCard
              key={key}
              title={label}
              icon={<CheckCircle2 size={14} className="text-pixiu" />}
              content={content}
              detailsTitle="展开章节解构"
              defaultExpanded={key === 'abstract'}
            />
          );
        })}

        <p className="theme-text-muted pb-4 text-center text-[10px]">以上内容由 AI 自动生成，请结合原文进行参考。</p>
      </div>
    </div>
  );
};

export default PaperAnalysis;
