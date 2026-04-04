import React, { useState } from 'react';
import { ChevronRight, Loader2, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const SocraticQuestionsPanel = ({
  hasPaperContext = false,
  isLoading = false,
  isChatLoading = false,
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

    const progress = readingProgress.trim() || '已完成概览阅读，正在深入理解研究方法与核心结论。';
    try {
      await onGenerate(progress);
    } catch (error) {
      setLocalError(error?.message || '生成失败，请稍后重试。');
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-slate-50/30">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-white px-6 py-4">
        <h2 className="flex items-center gap-2 text-lg font-bold text-slate-800">
          <Sparkles className="text-pixiu" size={20} />
          引导式学习
        </h2>
        <span className="rounded-full bg-pixiu/10 px-2 py-0.5 text-[10px] font-bold text-pixiu">
          苏格拉底式提问
        </span>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
          <div className="mb-3 text-sm font-bold text-slate-700">阅读进度（用于生成问题的难度与方向）</div>
          <textarea
            value={readingProgress}
            onChange={(event) => setReadingProgress(event.target.value)}
            rows={4}
            disabled={isLoading}
            className="w-full rounded-xl border border-slate-200 p-3 text-sm outline-none focus:ring-2 focus:ring-pixiu/20 disabled:bg-slate-50"
            placeholder="例如：我已阅读摘要与引言，理解了研究问题；接下来准备重点看方法部分。"
          />

          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={handleGenerate}
              disabled={isLoading || isChatLoading}
              className="flex items-center gap-2 rounded-xl bg-pixiu px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? <Loader2 className="animate-spin" size={18} /> : <Sparkles size={18} />}
              生成引导问题
            </button>
            {localError && (
              <div className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-600">
                {localError}
              </div>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
          <div className="mb-3 text-sm font-bold text-slate-700">生成的问题（点击可直接追问）</div>

          {isLoading && (
            <div className="flex items-center gap-3 text-sm text-slate-600">
              <Loader2 className="animate-spin text-pixiu" size={18} />
              正在生成问题...
            </div>
          )}

          {!isLoading && (!questions || questions.length === 0) && (
            <div className="text-sm text-slate-500">
              点击“生成引导问题”后，这里会展示由 AI 生成的苏格拉底式追问。
            </div>
          )}

          {!isLoading && questions && questions.length > 0 && (
            <div className="space-y-3">
              {questions.map((question, index) => (
                <div
                  key={`${index}-${question}`}
                  className="rounded-xl border border-slate-200 px-4 py-3 transition hover:border-pixiu/50 hover:bg-pixiu/5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-sm font-semibold text-slate-800">问题 {index + 1}：</div>
                  </div>
                  <div className="prose prose-sm mt-2 max-w-none text-sm text-slate-700">
                    <ReactMarkdown>{question}</ReactMarkdown>
                  </div>
                  <button
                    onClick={() => onAskQuestion?.(question)}
                    disabled={isChatLoading}
                    className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-pixiu py-2 font-medium text-white shadow-sm transition-all hover:bg-pixiu-dark disabled:opacity-50"
                  >
                    回答此问题 <ChevronRight size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SocraticQuestionsPanel;
