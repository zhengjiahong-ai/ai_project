import React from 'react';
import { FileText, CheckCircle2, Loader2, LayoutDashboard } from 'lucide-react';
import MarkdownContent from './MarkdownContent';

// 接收 App.jsx 传下来的 data 和 isLoading
const PaperAnalysis = ({ data, isLoading }) => {
  
  // 1. 加载状态
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-slate-500 font-medium">
        <Loader2 className="animate-spin mb-4 text-pixiu" size={40} />
        <p className="text-sm font-medium">🚀 大模型正在解构论文，请稍候（约 15-30s）...</p>
      </div>
    );
  }

  // 2. 空状态
  if (!data || !data.paper_skeleton) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-slate-400">
        <FileText size={48} className="mb-4 opacity-20" />
        <p>请先在导航栏上传 PDF 论文以生成深度解构报告</p>
      </div>
    );
  }

  const sectionLabels = {
    abstract: '摘要 (Abstract)',
    introduction: '引言 (Introduction)',
    methods: '方法 (Methods)',
    results: '结果 (Results)',
    discussion: '讨论 (Discussion)',
    conclusion: '结论 (Conclusion)'
  };

  return (
    <div className="h-full flex flex-col bg-slate-50/30 overflow-hidden">
      {/* 头部标题 */}
      <div className="px-6 py-4 bg-white border-b flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-3 mb-6 bg-pixiu/5 p-4 rounded-2xl border border-pixiu/10">
          <div className="w-10 h-10 bg-pixiu text-white rounded-xl flex items-center justify-center shadow-lg">
            <LayoutDashboard size={20} />
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-800">篇章逻辑解构</h2>
            <p className="text-xs text-slate-500 font-medium">深度拆解论文架构，洞察核心逻辑点</p>
          </div>
        </div>
        <span className="text-[10px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-bold">AI 已完成</span>
      </div>

      {/* 滚动内容区 */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {Object.entries(sectionLabels).map(([key, label]) => {
          const content = data.paper_skeleton[key];
          // 过滤掉无效内容
          if (!content || content.includes("请提供具体内容")) return null;

          return (
            <div key={key} className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100 transition-hover hover:shadow-md">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                <CheckCircle2 size={14} className="text-pixiu" /> {label}
              </h3>
              <div className="text-sm text-slate-700 leading-relaxed bg-pixiu/5 p-4 rounded-xl border-l-4 border-pixiu">
                <div 
                  className="h-2 rounded-full bg-pixiu transition-all duration-1000"
                />
                <MarkdownContent>{content}</MarkdownContent>
              </div>
            </div>
          );
        })}
        
        {/* 底部提示 */}
        <p className="text-center text-[10px] text-slate-400 pb-4">
          以上内容由 AI 自动生成，请结合原文进行参考
        </p>
      </div>
    </div>
  );
};

export default PaperAnalysis;
