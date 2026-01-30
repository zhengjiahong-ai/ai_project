import React from 'react';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, Cell 
} from 'recharts';
import { 
  Loader2, 
  BarChart3, 
  LayoutDashboard, 
  FileText, 
  AlertCircle, 
  CheckCircle2 
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';

/**
 * 批判性分析面板组件
 * @param {Object} data - 后端传回的分析数据
 * @param {Function} onAnalyze - 触发分析的函数
 * @param {Boolean} isLoading - 加载状态
 */
const CriticalAnalysisPanel = ({ data, onAnalyze, isLoading }) => {
  
  // 1. 初始未分析状态
  if (!data && !isLoading) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-center bg-slate-50">
        <div className="w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center mb-6 animate-pulse">
          <LayoutDashboard className="text-blue-600" size={40} />
        </div>
        <h3 className="text-xl font-bold text-slate-800">开启深度批判性阅读</h3>
        <p className="text-sm text-slate-500 mt-2 mb-8 max-w-xs">
          AI 将从创新性、逻辑严谨性、数据可靠性等维度对整篇论文进行深度解剖。
        </p>
        <button 
          onClick={onAnalyze}
          className="flex items-center gap-2 px-8 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all shadow-lg hover:shadow-blue-200 active:scale-95 font-semibold"
        >
          <BarChart3 size={20} />
          立即开始分析
        </button>
      </div>
    );
  }

  // 2. 加载中状态
  if (isLoading) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 bg-white text-center">
        <div className="relative mb-6">
          <Loader2 className="animate-spin text-blue-500" size={48} />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-2 h-2 bg-blue-500 rounded-full animate-ping"></div>
          </div>
        </div>
        <p className="text-lg font-medium text-slate-700">正在构建逻辑模型...</p>
        <p className="text-xs text-slate-400 mt-2">AI 正在阅读全文并提取批判性视角</p>
      </div>
    );
  }

  // 3. 分析结果展示状态
  return (
    <div className="h-full flex flex-col bg-slate-50/30">
      {/* 头部标题 */}
      <div className="px-6 py-4 bg-white border-b flex items-center justify-between sticky top-0 z-10">
        <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
          <FileText className="text-blue-600" size={20} />
          批判性阅读报告
        </h2>
        <span className="text-[10px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-bold">已生成</span>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        
        {/* 文字总结卡片 */}
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <CheckCircle2 size={14} className="text-green-500" /> 核心结论总结
          </h3>
          <div className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-4 rounded-xl border-l-4 border-blue-400">
            <div className="prose prose-sm max-w-none">
                <ReactMarkdown>{data.summary}</ReactMarkdown>
            </div>
          </div>
        </div>

        {/* 可视化图表卡片 */}
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">多维度评价</h3>
            <span className="text-[10px] text-slate-400 italic">鼠标悬停查看详情</span>
          </div>
          
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.metrics} layout="vertical" margin={{ left: -20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                <XAxis type="number" domain={[0, 100]} hide />
                <YAxis 
                  dataKey="name" 
                  type="category" 
                  width={80} 
                  tick={{ fontSize: 11, fontWeight: 600, fill: '#64748b' }} 
                />
                <Tooltip 
                  cursor={{ fill: '#f1f5f9', opacity: 0.5 }}
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const item = payload[0].payload;
                      return (
                        <div className="bg-slate-900 text-white p-3 rounded-xl shadow-2xl text-xs max-w-[220px] animate-in fade-in slide-in-from-bottom-1">
                          <div className="flex justify-between items-center mb-1.5 font-bold border-b border-white/10 pb-1.5">
                            <span>{item.name}</span>
                            <span className="text-blue-400">{item.score}分</span>
                          </div>
                          <p className="opacity-80 leading-normal">{item.detail}</p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Bar dataKey="score" radius={[0, 6, 6, 0]} barSize={20}>
                  {data.metrics.map((entry, index) => (
                    <Cell 
                      key={`cell-${index}`} 
                      // 根据得分动态改变颜色
                      fill={entry.score >= 80 ? '#3b82f6' : entry.score >= 60 ? '#6366f1' : '#94a3b8'} 
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 提示卡片 */}
        <div className="bg-amber-50 p-4 rounded-xl border border-amber-100 flex gap-3">
          <AlertCircle className="text-amber-500 shrink-0" size={18} />
          <p className="text-[11px] text-amber-700 leading-normal">
            提示：分析结果由 AI 基于全文逻辑推导生成，建议结合 PDF 中的具体划词解释功能进行深度对比。
          </p>
        </div>
      </div>
    </div>
  );
};

export default CriticalAnalysisPanel;