import React from 'react';
import { CheckCircle2, FileText, LayoutDashboard, Loader2 } from 'lucide-react';
import MarkdownContent from './MarkdownContent';

const PaperAnalysis = ({ data, isLoading }) => {
  if (isLoading) {
    return (
      <div className="theme-empty-state flex h-full flex-col items-center justify-center p-8 font-medium">
        <Loader2 className="mb-4 animate-spin text-pixiu" size={40} />
        <p className="text-sm font-medium">大模型正在解构论文，请稍候（约 15-30s）...</p>
      </div>
    );
  }

  if (!data || !data.paper_skeleton) {
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
        {Object.entries(sectionLabels).map(([key, label]) => {
          const content = data.paper_skeleton[key];
          if (!content || content.includes('请提供具体内容')) return null;

          return (
            <div key={key} className="theme-card rounded-2xl p-5 transition hover:shadow-md">
              <h3 className="theme-text-muted mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
                <CheckCircle2 size={14} className="text-pixiu" /> {label}
              </h3>
              <div className="theme-markdown-panel rounded-xl border-l-4 border-pixiu p-4 text-sm leading-relaxed">
                <div className="mb-3 h-2 rounded-full bg-pixiu" />
                <MarkdownContent>{content}</MarkdownContent>
              </div>
            </div>
          );
        })}

        <p className="theme-text-muted pb-4 text-center text-[10px]">以上内容由 AI 自动生成，请结合原文进行参考。</p>
      </div>
    </div>
  );
};

export default PaperAnalysis;
