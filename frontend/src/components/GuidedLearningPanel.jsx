import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { apiService } from '../services/api';

export default function GuidedLearningPanel({ paperHtml, deconstructData, isLoadingDeconstruct }) {
  const [readingProgress, setReadingProgress] = useState('我刚刚读完了摘要和引言部分，希望了解本文关于核心方法的设计思路。');
  const [questions, setQuestions] = useState([]);
  const [ragSources, setRagSources] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleGenerateQuestions = async () => {
    setIsLoading(true);
    setError('');
    
    try {
      // 提取论文内容，优先使用结构化解析文本
      let contentParts = [];
      
      if (deconstructData && deconstructData.paper_skeleton) {
          const skel = deconstructData.paper_skeleton;
          if (skel.abstract) contentParts.push(`【摘要】: ${skel.abstract}`);
          if (skel.introduction) contentParts.push(`【引言】: ${skel.introduction}`);
          if (skel.conclusion) contentParts.push(`【结论】: ${skel.conclusion}`);
      }
      
      // 尝试从 paper_structure 进一步完善上下文
      if (deconstructData && deconstructData.paper_structure) {
          const struct = deconstructData.paper_structure;
          if (struct.research_problem) contentParts.push(`【研究问题】: ${struct.research_problem}`);
          if (struct.core_hypothesis) contentParts.push(`【核心假设】: ${struct.core_hypothesis}`);
      }
      
      let paperContent = contentParts.join("\n\n");
      
      // 如果 skeleton 还是没内容，尝试用 paperHtml 兜底
      if (!paperContent || paperContent.length < 50) {
          paperContent = paperHtml ? paperHtml.substring(0, 4000) : "";
      }
      
      if (!paperContent || paperContent.length < 20) {
        throw new Error("未能获取到论文分析内容。请确认论文已完成篇章解构（可在左侧‘篇章解构’标签查看状态）。");
      }

      const response = await apiService.getSocraticQuestions(paperContent, readingProgress);
      
      if (response && response.status === 'success') {
        setQuestions(response.questions || []);
        setRagSources(response.rag_sources || []);
      } else {
        throw new Error(response?.message || '生成提问失败');
      }
    } catch (err) {
      console.error(err);
      setError(err.message || '系统错误，请检查网络或后端服务是否正常。');
    } finally {
      setIsLoading(false);
    }
  };

  // 如果主文件正在解构中，显示全局加载状态
  if (isLoadingDeconstruct) {
    return (
      <div className="flex flex-col h-full items-center justify-center bg-[#FAFAFA] p-8 text-center">
        <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mb-4"></div>
        <h3 className="text-slate-700 font-bold mb-2">正在深度解析论文...</h3>
        <p className="text-xs text-slate-500">AI 正在提取论文结构，完成后即可开始引导式学习。</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#FAFAFA] text-slate-800">
      {/* 标题栏 */}
      <div className="p-4 bg-white border-b border-slate-200 flex flex-col gap-2 shrink-0 shadow-sm z-10">
        <h2 className="text-lg font-bold flex items-center gap-2 text-indigo-700">
           引导式学习 🧠 
        </h2>
        <p className="text-xs text-slate-500">
          基于当前论文内容和您的阅读进度，为您自动生成苏格拉底式启发问题。
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        
        {/* 阅读进度输入区 */}
        <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200">
          <label className="block text-sm font-semibold text-slate-700 mb-2">
            🔖 您的当前阅读进度或关注点：
          </label>
          <textarea
            className="w-full bg-slate-50 border border-slate-300 rounded-lg p-3 text-sm min-h-[80px] focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
            value={readingProgress}
            onChange={(e) => setReadingProgress(e.target.value)}
            placeholder="例如：我刚看完引言，想搞明白作者提出的假设..."
          />
          <button
            onClick={handleGenerateQuestions}
            disabled={isLoading}
            className={`mt-4 w-full py-2.5 rounded-lg text-white font-medium transition-colors ${
              isLoading 
                ? 'bg-indigo-300 cursor-not-allowed' 
                : 'bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 shadow-md transform active:scale-[0.99]'
            }`}
          >
            {isLoading ? '⏳ 正在深思熟虑生成提问...' : '✨ 生成苏格拉底提问'}
          </button>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="bg-red-50 text-red-600 p-3 rounded-lg text-sm border border-red-200">
             发生错误：{error}
          </div>
        )}

        {/* 问题展示区 */}
        {questions.length > 0 && (
          <div className="space-y-4">
            <h3 className="font-bold text-slate-700 border-b border-slate-200 pb-2">🎯 启发性追问</h3>
            <div className="space-y-3">
              {questions.map((q, idx) => {
                // 如果问题带有特殊排版或数字开头，可稍微清理一下，这里简单展示
                return (
                  <div key={idx} className="group relative bg-indigo-50/50 p-4 rounded-xl border border-indigo-100 hover:bg-indigo-50 transition-colors">
                    <div className="absolute -left-2 -top-2 w-6 h-6 bg-indigo-500 text-white rounded-full flex items-center justify-center text-xs font-bold shadow-sm">
                      Q{idx + 1}
                    </div>
                    <div className="text-sm leading-relaxed text-slate-700 [&>p]:my-1 [&>strong]:font-semibold [&>strong]:text-slate-900 [&>ul]:list-disc [&>ul]:pl-4 [&>ol]:list-decimal [&>ol]:pl-4 [&>li]:mt-0.5">
                      <ReactMarkdown>{q.replace(/^\d+\.\s*/, '')}</ReactMarkdown>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* RAG 文献溯源 */}
        {ragSources && ragSources.length > 0 && (
          <div className="pt-4 mt-6 border-t border-slate-200">
            <h3 className="font-semibold text-xs text-slate-400 mb-3 uppercase tracking-wider">📚 知识来源辅助参考</h3>
            <div className="space-y-2">
              {ragSources.map((source, idx) => (
                <div key={idx} className="bg-white p-3 rounded border border-slate-200 shadow-sm">
                  <p className="text-xs text-slate-600 line-clamp-3 italic">"...{source.text}..."</p>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
