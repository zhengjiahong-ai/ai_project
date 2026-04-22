import React, { useMemo, useState } from 'react';
import { ChevronRight, Loader2, RotateCcw, Sparkles } from 'lucide-react';
import MarkdownContent from './MarkdownContent';

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
  reviewSuggestions: [],
  isComplete: false,
};

const masteryToneMap = {
  需加强: 'border-amber-400/25 bg-amber-500/10 text-amber-500',
  一般: 'border-sky-400/25 bg-sky-500/10 text-sky-400',
  较好: 'border-emerald-400/25 bg-emerald-500/10 text-emerald-400',
};

const evidenceToneMap = {
  CORRECT: 'border-emerald-400/25 bg-emerald-500/10 text-emerald-400',
  AMBIGUOUS: 'border-amber-400/25 bg-amber-500/10 text-amber-500',
  INCORRECT: 'border-rose-400/25 bg-rose-500/10 text-rose-400',
};

const evidenceVerdictLabelMap = {
  CORRECT: '证据充足',
  AMBIGUOUS: '部分相关',
  INCORRECT: '证据不足',
};

const formatEvidenceQuality = (quality) => {
  if (!quality || typeof quality !== 'object') {
    return null;
  }

  const verdict = `${quality.verdict ?? ''}`.trim().toUpperCase();
  const reason = `${quality.reason ?? ''}`.trim();
  const confidence = Number(quality.confidence);

  if (!verdict && !reason && !Number.isFinite(confidence)) {
    return null;
  }

  return {
    verdict,
    verdictLabel: evidenceVerdictLabelMap[verdict] || '证据判断',
    toneClass: evidenceToneMap[verdict] || 'theme-card-soft',
    reason,
    confidence: Number.isFinite(confidence) ? Math.round(confidence * 100) : null,
  };
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
      setAnswerDraft('');
    } catch (error) {
      setSubmitError(error?.message || '提交回答失败，请稍后重试。');
    }
  };

  return (
    <div className="theme-card rounded-xl border border-pixiu/20 px-4 py-4 ring-1 ring-pixiu/10">
      <div className="theme-text-primary mb-2 text-sm font-semibold">问题 {index}：</div>
      <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">{question}</MarkdownContent>

      <div className="mt-4">
        <div className="theme-text-secondary mb-2 text-xs font-semibold tracking-wide">请输入你的回答</div>
        <textarea
          value={answerDraft}
          onChange={(event) => setAnswerDraft(event.target.value)}
          rows={5}
          disabled={isLoading}
          className="theme-input w-full rounded-xl p-3 text-sm outline-none transition"
          placeholder="尝试用你自己的话作答。可以先说你理解的核心问题、方法逻辑，再补充证据或疑问。"
        />
      </div>

      {submitError && <div className="mt-4 rounded-lg border border-red-400/20 bg-red-500/10 px-3 py-2 text-xs text-red-500">{submitError}</div>}

      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={handleSubmit}
          disabled={isLoading || !answerDraft.trim()}
          className="flex items-center gap-2 rounded-xl bg-pixiu px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? <Loader2 className="animate-spin" size={18} /> : <ChevronRight size={18} />}
          提交回答
        </button>
        <span className="theme-text-secondary text-xs">提交后，AI 会先评估你的掌握程度，再继续追问。</span>
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

  const renderCompletedCard = (turn) => {
    const evidenceQuality = formatEvidenceQuality(turn.evidenceQuality);

    return (
      <div key={`turn-${turn.index}`} className="theme-card rounded-xl px-4 py-4">
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="theme-text-primary text-sm font-semibold">问题 {turn.index}：</div>
          <span
            className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
              masteryToneMap[turn.masteryLevel] || 'theme-card-soft'
            }`}
          >
            掌握度：{turn.masteryLevel || '一般'}
          </span>
        </div>

        <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">{turn.question}</MarkdownContent>

        <div className="theme-card-soft mt-4 rounded-xl px-4 py-3">
          <div className="theme-text-secondary mb-2 text-xs font-semibold tracking-wide">你的回答</div>
          <div className="theme-text-secondary whitespace-pre-wrap text-sm leading-7">{turn.answer}</div>
        </div>

        <div className="mt-4 space-y-3">
          <div className="theme-markdown-panel rounded-xl border border-pixiu/10 px-4 py-3">
            <div className="mb-1 text-xs font-semibold tracking-wide text-pixiu">AI 简评</div>
            <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
              {turn.feedback || '这一轮已完成。'}
            </MarkdownContent>
          </div>

          <div className="theme-card-soft rounded-xl px-4 py-3">
            <div className="theme-text-secondary mb-1 text-xs font-semibold tracking-wide">下一步提示</div>
            <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
              {turn.hint || '继续结合论文原文梳理关键逻辑。'}
            </MarkdownContent>
          </div>

          {evidenceQuality && (
            <div className="theme-card-soft rounded-xl px-4 py-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="theme-text-secondary text-xs font-semibold tracking-wide">证据判断</div>
                <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${evidenceQuality.toneClass}`}>
                  {evidenceQuality.verdictLabel}
                  {evidenceQuality.confidence !== null && ` · ${evidenceQuality.confidence}%`}
                </span>
              </div>
              <div className="theme-text-secondary text-sm leading-7">
                {evidenceQuality.reason || '当前轮次未提供额外证据说明。'}
              </div>
            </div>
          )}

          {Array.isArray(turn.missingAspects) && turn.missingAspects.length > 0 && (
            <div className="theme-card-soft rounded-xl px-4 py-3">
              <div className="theme-text-secondary mb-1 text-xs font-semibold tracking-wide">仍需补强</div>
              <div className="theme-text-secondary text-sm leading-7">{turn.missingAspects.join('、')}</div>
            </div>
          )}
        </div>
      </div>
    );
  };

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
    <div key={`locked-${index}`} className="theme-card-soft rounded-xl border-dashed px-4 py-4">
      <div className="theme-text-primary text-sm font-semibold">问题 {index}：</div>
      <div className="theme-text-secondary mt-2 text-sm">完成前一题后，这一题会自动解锁。</div>
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
    <div className="theme-panel-muted flex h-full flex-col overflow-hidden">
      <div className="theme-panel theme-border sticky top-0 z-10 flex items-center justify-between border-b px-6 py-4">
        <h2 className="theme-text-primary flex items-center gap-2 text-lg font-bold">
          <Sparkles className="text-pixiu" size={20} />
          引导式学习
        </h2>
        <span className="rounded-full bg-pixiu/10 px-2 py-0.5 text-[10px] font-bold text-pixiu">苏格拉底式提问</span>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        <div className="theme-card rounded-2xl p-5">
          <div className="theme-text-primary mb-3 text-sm font-bold">阅读进度</div>
          <textarea
            value={sessionData.readingProgress || ''}
            onChange={(event) => onReadingProgressChange?.(event.target.value)}
            rows={4}
            disabled={isLoading || sessionData.started}
            className="theme-input w-full rounded-xl p-3 text-sm outline-none"
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
                className="theme-button-secondary flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RotateCcw size={16} />
                重新开始
              </button>
            )}

            <span className="theme-text-secondary text-xs">
              {sessionData.started
                ? '阅读进度已锁定，当前会话会根据你的回答持续推进。'
                : '先填写当前阅读进度，AI 会据此决定提问起点和难度。'}
            </span>
          </div>

          {localError && <div className="mt-4 rounded-lg border border-red-400/20 bg-red-500/10 px-3 py-2 text-xs text-red-500">{localError}</div>}
        </div>

        <div className="theme-card rounded-2xl p-5">
          <div className="theme-text-primary mb-3 text-sm font-bold">学习引导</div>
          <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
            {sessionData.intro || '我会根据你的阅读进度逐步提问。你先作答，我会判断掌握程度，再继续追问。'}
          </MarkdownContent>
        </div>

        <div className="theme-card rounded-2xl p-5">
          <div className="theme-text-primary mb-3 text-sm font-bold">引导问题</div>

          {!sessionData.started && (
            <div className="theme-text-secondary text-sm">
              点击“开始引导学习”后，这里会展示当前问题、你的回答，以及 AI 对掌握程度的判断。
            </div>
          )}

          {sessionData.started && <div className="space-y-3">{cards}</div>}
        </div>

        <div className="theme-card rounded-2xl p-5">
          <div className="theme-text-primary mb-3 text-sm font-bold">总结</div>
          {sessionData.isComplete ? (
            <div className="space-y-4">
              <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
                {sessionData.finalSummary || '本轮引导学习已完成。'}
              </MarkdownContent>

              {Array.isArray(sessionData.reviewSuggestions) && sessionData.reviewSuggestions.length > 0 && (
                <div className="theme-card-soft rounded-xl px-4 py-3">
                  <div className="theme-text-secondary mb-2 text-xs font-semibold tracking-wide">建议回读</div>
                  <div className="space-y-2">
                    {sessionData.reviewSuggestions.map((item, index) => (
                      <div key={`review-${index}`} className="theme-text-secondary text-sm leading-7">
                        {item}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="theme-text-secondary text-sm">完成 5 个问题后，AI 会在这里给出整体掌握情况总结。</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SocraticQuestionsPanel;
