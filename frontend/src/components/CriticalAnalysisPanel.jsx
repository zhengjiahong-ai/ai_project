import React from 'react';
import { AlertCircle, FileText, Loader2, ShieldAlert } from 'lucide-react';
import ReactMarkdown from 'react-markdown';


const markdownBlockClassName =
  'prose prose-sm max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-li:text-slate-700';

const SectionCard = ({ title, content }) => (
  <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
    <h3 className="mb-3 text-sm font-semibold text-slate-900">{title}</h3>
    <div className={markdownBlockClassName}>
      <ReactMarkdown>{content || '暂无内容。'}</ReactMarkdown>
    </div>
  </section>
);


const CriticalAnalysisPanel = ({ data, onAnalyze, isLoading }) => {
  if (!data && !isLoading) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-slate-50 px-8 text-center">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-pixiu/10">
          <ShieldAlert size={36} className="text-pixiu" />
        </div>
        <h3 className="text-xl font-bold text-slate-900">开始批判性阅读</h3>
        <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">
          点击后会调用后端真实分析链路，从论文全文中提取作者宣称贡献、推断真实贡献，并生成批判性阅读结论。
        </p>
        <button
          onClick={onAnalyze}
          className="mt-8 rounded-xl bg-pixiu px-6 py-3 font-semibold text-white transition hover:bg-pixiu-dark"
        >
          运行真实分析
        </button>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-white px-8 text-center">
        <Loader2 size={42} className="animate-spin text-pixiu" />
        <p className="mt-4 text-lg font-medium text-slate-800">正在生成批判性阅读结果...</p>
        <p className="mt-2 text-sm text-slate-500">系统会先定位论文内容，再调用深度分析接口。</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-slate-50">
      <div className="flex items-center justify-between border-b bg-white px-6 py-4">
        <h2 className="flex items-center gap-2 text-lg font-bold text-slate-900">
          <FileText size={18} className="text-pixiu" />
          批判性阅读报告
        </h2>
        <button
          onClick={onAnalyze}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:border-pixiu hover:text-pixiu"
        >
          重新分析
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        <SectionCard title="作者宣称的贡献" content={data?.claimed_contributions} />
        <SectionCard title="推断出的真实贡献" content={data?.inferred_real_contributions} />
        <SectionCard title="批判性阅读结论" content={data?.critical_analysis} />

        <div className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div className="space-y-1">
            <p>本结果来自真实后端分析链路，而不是前端 mock。</p>
            <p>如需追溯，请结合右侧对话和论文原文继续追问具体论证、实验或结论细节。</p>
          </div>
        </div>
      </div>
    </div>
  );
};


export default CriticalAnalysisPanel;
