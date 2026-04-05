import React, { useMemo, useState } from 'react';
import { ChevronRight, Loader2, RotateCcw, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const DEFAULT_TOTAL_QUESTIONS = 5;

const emptySession = {
  started: false,
  readingProgress: '',
  intro: '',
  totalQuestions: DEFAULT_TOTAL_QUESTIONS,
  currentIndex: 1,
  currentQuestion: '',
  turns: [],
  finalSummary: '',
  isComplete: false,
};

const masteryToneMap = {
  '需加强': 'border-amber-200 bg-amber-50 text-amber-700',
  '一般': 'border-sky-200 bg-sky-50 text-sky-700',
  '较好': 'border-emerald-200 bg-emerald-50 text-emerald-700',
};

const CurrentQuestionCard = ({ index, question, isLoading, onSubmit }) => {
  const [answerDraft, setAnswerDraft] = useState('');
  const [submitError, setSubmitError] = useState(null);

  const handleSubmit = async () => {
    setSubmitError(null);
    if (!answerDraft.trim()) {
      setSubmitError('请先输入你的回答，再继续下一步。');
      return;
    }

    try {
      await onSubmit?.(answerDraft.trim());
    } catch (error) {
      setSubmitError(error?.message || '提交回答失败，请稍后重试。');
    }
  };

  return (
    <div className="rounded-xl border border-pixiu/20 bg-white px-4 py-4 shadow-sm ring-1 ring-pixiu/10">
      <div className="mb-2 text-sm font-semibold text-slate-800">问题 {index}：</div>
      <div className="prose prose-sm max-w-none text-sm text-slate-700">
        <ReactMarkdown>{question}</ReactMarkdown>
      </div>

      <div className="mt-4">
        <div className="mb-2 text-xs font-semibold tracking-wide text-slate-500">请输入你的回答</div>
        <textarea
          value={answerDraft}
          onChange={(event) => setAnswerDraft(event.target.value)}
          rows={5}
          disabled={isLoading}
          className="w-full rounded-xl border border-slate-200 p-3 text-sm outline-none transition focus:ring-2 focus:ring-pixiu/20 disabled:bg-slate-50"
          placeholder="尝试用你自己的话作答。可以先说你理解的核心问题、方法逻辑，再补充证据或疑问。"
        />
      </div>

      {submitError && (
        <div className="mt-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-600">
          {submitError}
        </div>
      )}

      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={handleSubmit}
          disabled={isLoading || !answerDraft.trim()}
          className="flex items-center gap-2 rounded-xl bg-pixiu px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? <Loader2 className="animate-spin" size={18} /> : <ChevronRight size={18} />}
          提交回答
        </button>
        <span className="text-xs text-slate-500">提交后，AI 会先评估你的掌握程度，再继续追问。</span>
      </div>
    </div>
  );
};

const SocraticQuestionsPanel = ({
  hasPaperContext = false,
  isLoading = false,
  session = emptySession,
  onReadingProgressChange,
  onStart,
  onSubmitAnswer,
  onRestart,
}) => {
  const sessionData = session || emptySession;
  const totalQuestions = sessionData.totalQuestions || DEFAULT_TOTAL_QUESTIONS;
  const [localError, setLocalError] = useState(null);

  const turnsByIndex = useMemo(
    () => new Map((sessionData.turns || []).map((turn) => [turn.index, turn])),
    [sessionData.turns],
  );

  const handleStart = async () => {
    setLocalError(null);
    if (!hasPaperContext) {
      setLocalError('请先完成“篇章解构”，系统需要论文结构内容来生成引导学习问题。');
      return;
    }

    try {
      await onStart?.(sessionData.readingProgress);
    } catch (error) {
      setLocalError(error?.message || '启动引导学习失败，请稍后重试。');
    }
  };

  const renderCompletedCard = (turn) => (
    <div
      key={`turn-${turn.index}`}
      className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm"
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-slate-800">问题 {turn.index}：</div>
        <span
          className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
            masteryToneMap[turn.masteryLevel] || 'border-slate-200 bg-slate-50 text-slate-600'
          }`}
        >
          掌握度：{turn.masteryLevel || '一般'}
        </span>
      </div>

      <div className="prose prose-sm max-w-none text-sm text-slate-700">
        <ReactMarkdown>{turn.question}</ReactMarkdown>
      </div>

      <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
        <div className="mb-2 text-xs font-semibold tracking-wide text-slate-500">你的回答</div>
        <div className="text-sm leading-7 text-slate-700 whitespace-pre-wrap">{turn.answer}</div>
      </div>

      <div className="mt-4 space-y-3">
        <div className="rounded-xl border border-pixiu/10 bg-pixiu/5 px-4 py-3">
          <div className="mb-1 text-xs font-semibold tracking-wide text-pixiu">AI 简评</div>
          <div className="prose prose-sm max-w-none text-sm text-slate-700">
            <ReactMarkdown>{turn.feedback || '这一轮已完成。'}</ReactMarkdown>
          </div>
        </div>

        <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
          <div className="mb-1 text-xs font-semibold tracking-wide text-slate-500">下一步提示</div>
          <div className="prose prose-sm max-w-none text-sm text-slate-700">
            <ReactMarkdown>{turn.hint || '继续结合论文原文梳理关键逻辑。'}</ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );

  const renderCurrentQuestionCard = (index) => (
    <CurrentQuestionCard
      key={`current-${index}-${sessionData.currentQuestion}`}
      index={index}
      question={sessionData.currentQuestion}
      isLoading={isLoading}
      onSubmit={onSubmitAnswer}
    />
  );

  const renderLockedCard = (index) => (
    <div
      key={`locked-${index}`}
      className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 px-4 py-4"
    >
      <div className="text-sm font-semibold text-slate-700">问题 {index}：</div>
      <div className="mt-2 text-sm text-slate-500">完成前一题后，这一题会自动解锁。</div>
    </div>
  );

  const cards = [];
  for (let index = 1; index <= totalQuestions; index += 1) {
    const completedTurn = turnsByIndex.get(index);
    if (completedTurn) {
      cards.push(renderCompletedCard(completedTurn));
      continue;
    }

    if (!sessionData.isComplete && sessionData.started && index === sessionData.currentIndex) {
      cards.push(renderCurrentQuestionCard(index));
      continue;
    }

    cards.push(renderLockedCard(index));
  }

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
          <div className="mb-3 text-sm font-bold text-slate-700">阅读进度</div>
          <textarea
            value={sessionData.readingProgress || ''}
            onChange={(event) => onReadingProgressChange?.(event.target.value)}
            rows={4}
            disabled={isLoading || sessionData.started}
            className="w-full rounded-xl border border-slate-200 p-3 text-sm outline-none focus:ring-2 focus:ring-pixiu/20 disabled:bg-slate-50"
            placeholder="例如：我已经看完摘要和引言，理解了研究问题；接下来准备重点读方法和实验部分。"
          />

          <div className="mt-4 flex flex-wrap items-center gap-3">
            {!sessionData.started && (
              <button
                onClick={handleStart}
                disabled={isLoading}
                className="flex items-center gap-2 rounded-xl bg-pixiu px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isLoading ? <Loader2 className="animate-spin" size={18} /> : <Sparkles size={18} />}
                开始引导学习
              </button>
            )}

            {sessionData.started && (
              <button
                onClick={onRestart}
                disabled={isLoading}
                className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-pixiu/30 hover:text-pixiu disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RotateCcw size={16} />
                重新开始
              </button>
            )}

            <span className="text-xs text-slate-500">
              {sessionData.started
                ? '阅读进度已锁定，当前会话会根据你的回答持续推进。'
                : '先填写当前阅读进度，AI 会据此决定提问起点和难度。'}
            </span>
          </div>

          {localError && (
            <div className="mt-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-600">
              {localError}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
          <div className="mb-3 text-sm font-bold text-slate-700">学习引导</div>
          <div className="prose prose-sm max-w-none text-sm text-slate-700">
            <ReactMarkdown>
              {sessionData.intro || '我会根据你的阅读进度逐步提问。你先作答，我会判断掌握程度，再继续追问。'}
            </ReactMarkdown>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
          <div className="mb-3 text-sm font-bold text-slate-700">引导问题</div>

          {!sessionData.started && (
            <div className="text-sm text-slate-500">
              点击“开始引导学习”后，这里会展示当前问题、你的回答，以及 AI 对掌握程度的判断。
            </div>
          )}

          {sessionData.started && <div className="space-y-3">{cards}</div>}
        </div>

        <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
          <div className="mb-3 text-sm font-bold text-slate-700">总结</div>
          {sessionData.isComplete ? (
            <div className="prose prose-sm max-w-none text-sm text-slate-700">
              <ReactMarkdown>{sessionData.finalSummary || '本轮引导学习已完成。'}</ReactMarkdown>
            </div>
          ) : (
            <div className="text-sm text-slate-500">完成 5 个问题后，AI 会在这里给出整体掌握情况总结。</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SocraticQuestionsPanel;
