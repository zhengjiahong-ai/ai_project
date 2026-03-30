import React, { useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const SocraticQuestionsPanel = ({
  hasPaperContext = false,
  isLoading = false,
  questions = [],
  onGenerate,
  onAskQuestion,
}) => {
  const [readingProgress, setReadingProgress] = useState('');
  const [localError, setLocalError] = useState(null);

  const handleGenerate = async () => {
    setLocalError(null);
    if (!hasPaperContext) {
      setLocalError('请先完成“篇章解构”，系统需要论文结构内容来生成问题。');
      return;
    }
    const rp = readingProgress?.trim();
    const progress = rp || '已完成概览阅读，正在深入理解研究方法与核心结论。';
    try {
      await onGenerate(progress);
    } catch (e) {
      setLocalError(e?.message || '生成失败，请稍后重试。');
    }
  };

  return (
    <div className="h-full flex flex-col bg-slate-50/30 overflow-hidden">
      <div className="px-6 py-4 bg-white border-b flex items-center justify-between sticky top-0 z-10">
        <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
          <Sparkles className="text-blue-600" size={20} />
          引导式学习
        </h2>
        <span className="text-[10px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-bold">
          苏格拉底式提问
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100">
          <div className="text-sm font-bold text-slate-700 mb-3">阅读进度（用于生成问题的难度与方向）</div>
          <textarea
            value={readingProgress}
            onChange={(e) => setReadingProgress(e.target.value)}
            rows={4}
            className="w-full border border-slate-200 rounded-xl p-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/20"
            placeholder="例如：我已阅读摘要与引言，理解了研究问题；接下来准备重点看方法部分。"
          />

          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={handleGenerate}
              disabled={isLoading}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition shadow-sm disabled:opacity-60 disabled:cursor-not-allowed font-semibold"
            >
              {isLoading ? <Loader2 className="animate-spin" size={18} /> : <Sparkles size={18} />}
              生成引导问题
            </button>
            {localError && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-100 px-3 py-2 rounded-lg">
                {localError}
              </div>
            )}
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100">
          <div className="text-sm font-bold text-slate-700 mb-3">生成的问题（点击可直接追问）</div>

          {isLoading && (
            <div className="flex items-center gap-3 text-sm text-slate-600">
              <Loader2 className="animate-spin text-blue-500" size={18} />
              正在生成问题...
            </div>
          )}

          {!isLoading && (!questions || questions.length === 0) && (
            <div className="text-sm text-slate-500">
              点击“生成引导问题”后，这里会展示由 AI 生成的 5 个苏格拉底式问题。
            </div>
          )}

          {!isLoading && questions && questions.length > 0 && (
            <div className="space-y-3">
              {questions.map((q, idx) => (
                <button
                  key={`${idx}-${q}`}
                  onClick={() => onAskQuestion?.(q)}
                  className="w-full text-left px-4 py-3 rounded-xl border border-slate-200 hover:border-blue-300 hover:bg-blue-50/40 transition"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-sm font-semibold text-slate-800">
                      问题 {idx + 1}：
                    </div>
                  </div>
                  <div className="mt-2 text-sm text-slate-700 prose prose-sm max-w-none">
                    <ReactMarkdown>{q}</ReactMarkdown>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SocraticQuestionsPanel;

