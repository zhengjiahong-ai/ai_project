import React, { useMemo, useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Loader2,
  RotateCcw,
  Sparkles,
} from 'lucide-react';

import MarkdownContent from './MarkdownContent';
import { getEvidenceVerdictMeta, getMasteryToneClass } from '../utils/socraticSessionModel';

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

const learningSteps = [
  { id: 'setup', label: '设置起点' },
  { id: 'answer', label: '回答问题' },
  { id: 'reflect', label: '查看反馈' },
  { id: 'wrap', label: '回顾总结' },
];

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

  const verdictMeta = getEvidenceVerdictMeta(verdict);

  return {
    verdict,
    verdictLabel: verdictMeta.label,
    toneClass: verdictMeta.toneClass,
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
      setSubmitError('请先写下你的回答，再进入下一步。');
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
    <div className="theme-card socratic-active-card rounded-2xl p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="theme-text-muted text-[11px] font-semibold uppercase tracking-wide">当前问题</div>
          <div className="theme-text-primary mt-1 text-sm font-bold">问题 {index}</div>
        </div>
      </div>

      <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">{question}</MarkdownContent>

      <div className="socratic-user-block mt-4 rounded-2xl p-4">
        <div className="theme-text-secondary mb-2 text-xs font-semibold tracking-wide">你的回答</div>
        <textarea
          value={answerDraft}
          onChange={(event) => setAnswerDraft(event.target.value)}
          rows={5}
          disabled={isLoading}
          className="theme-input w-full rounded-xl p-3 text-sm outline-none transition"
          placeholder="输入回答..."
        />
      </div>

      {submitError && (
        <div className="mt-4 rounded-lg border border-red-400/20 bg-red-500/10 px-3 py-2 text-xs text-red-500">
          {submitError}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isLoading || !answerDraft.trim()}
          className="flex items-center gap-2 rounded-xl bg-pixiu px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? <Loader2 className="animate-spin" size={18} /> : <ChevronRight size={18} />}
          提交回答
        </button>
      </div>
    </div>
  );
};

const TurnReviewCard = ({ turn, defaultOpen = false }) => {
  const [isExpanded, setIsExpanded] = useState(defaultOpen);
  const evidenceQuality = formatEvidenceQuality(turn.evidenceQuality);

  return (
    <div className="theme-card socratic-turn-card rounded-2xl p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="theme-text-primary text-sm font-semibold">问题 {turn.index}</span>
            <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${getMasteryToneClass(turn.masteryLevel)}`}>
              掌握度：{turn.masteryLevel || '一般'}
            </span>
          </div>
          <div className="theme-text-secondary text-sm leading-7">{turn.question}</div>
        </div>

        <button
          type="button"
          onClick={() => setIsExpanded((current) => !current)}
          className="theme-button-secondary inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
        >
          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {isExpanded ? '收起反馈' : '展开反馈'}
        </button>
      </div>

      <div className="socratic-user-summary mt-3 rounded-xl px-4 py-3">
        <div className="theme-text-secondary mb-1 text-xs font-semibold tracking-wide">你的回答摘要</div>
        <div className="theme-text-secondary line-clamp-3 text-sm leading-7">{turn.answer}</div>
      </div>

      {isExpanded && (
        <div className="mt-4 space-y-3">
          <div className="socratic-ai-feedback rounded-xl px-4 py-3">
            <div className="mb-1 text-xs font-semibold tracking-wide text-pixiu">AI 反馈</div>
            <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
              {turn.feedback || '这一轮已完成。'}
            </MarkdownContent>
          </div>

          <div className="socratic-next-step rounded-xl px-4 py-3">
            <div className="theme-text-secondary mb-1 text-xs font-semibold tracking-wide">下一步建议</div>
            <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
              {turn.hint || '继续结合原文梳理关键逻辑。'}
            </MarkdownContent>
          </div>

          {evidenceQuality && (
            <div className="socratic-evidence-block rounded-xl px-4 py-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="theme-text-secondary text-xs font-semibold tracking-wide">证据判断</div>
                <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${evidenceQuality.toneClass}`}>
                  {evidenceQuality.verdictLabel}
                  {evidenceQuality.confidence !== null && ` · ${evidenceQuality.confidence}%`}
                </span>
              </div>
              <div className="theme-text-secondary text-sm leading-7">
                {evidenceQuality.reason || '本轮暂未给出额外证据说明。'}
              </div>
            </div>
          )}

          {Array.isArray(turn.missingAspects) && turn.missingAspects.length > 0 && (
            <div className="socratic-gap-block rounded-xl px-4 py-3">
              <div className="theme-text-secondary mb-1 text-xs font-semibold tracking-wide">仍需补强</div>
              <div className="theme-text-secondary text-sm leading-7">{turn.missingAspects.join('、')}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const LockedStepCard = ({ index }) => (
  <div className="theme-card-soft socratic-locked-card rounded-2xl border-dashed px-4 py-4">
    <div className="theme-text-primary text-sm font-semibold">问题 {index}</div>
    <div className="theme-text-secondary mt-2 text-sm">完成上一题后，这一题会自动解锁。</div>
  </div>
);

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

  const completedCount = sessionData.turns?.length || 0;
  const progressPercent = Math.round((completedCount / Math.max(totalQuestions, 1)) * 100);

  const handleStart = async () => {
    setLocalError(null);
    if (!hasPaperContext) {
      setLocalError('请先完成篇章解构，系统需要论文结构来生成引导问题。');
      return;
    }

    try {
      await onStart?.(sessionData.readingProgress);
    } catch (error) {
      setLocalError(error?.message || '启动引导学习失败，请稍后再试。');
    }
  };

  const cards = [];
  for (let index = 1; index <= totalQuestions; index += 1) {
    const completedTurn = turnsByIndex.get(index);
    if (completedTurn) {
      cards.push(<TurnReviewCard key={`turn-${index}`} turn={completedTurn} defaultOpen={index === completedCount} />);
      continue;
    }

    if (!sessionData.isComplete && sessionData.started && index === sessionData.currentIndex) {
      cards.push(
        <CurrentQuestionCard
          key={`current-${index}-${sessionData.currentQuestion}`}
          index={index}
          question={sessionData.currentQuestion}
          isLoading={isLoading}
          onSubmit={onSubmitAnswer}
        />,
      );
      continue;
    }

    cards.push(<LockedStepCard key={`locked-${index}`} index={index} />);
  }

  return (
    <div className="theme-panel-muted flex h-full flex-col overflow-hidden">
      <div className="theme-panel theme-border sticky top-0 z-10 border-b px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="theme-text-primary flex items-center gap-2 text-lg font-bold">
              <Sparkles className="text-pixiu" size={20} />
              引导学习
            </h2>
            <p className="theme-text-secondary mt-1 text-xs">把后端提问逻辑拆成一轮一轮推进，让用户先思考、再作答、再接收反馈。</p>
          </div>
          <span className="rounded-full bg-pixiu/10 px-2.5 py-1 text-[10px] font-bold text-pixiu">苏格拉底式提问</span>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-4">
          {learningSteps.map((step, index) => {
            const isActive =
              (!sessionData.started && step.id === 'setup')
              || (sessionData.started && !sessionData.isComplete && index === 1)
              || (sessionData.started && completedCount > 0 && index === 2)
              || (sessionData.isComplete && step.id === 'wrap');

            return (
              <div
                key={step.id}
                className={`workflow-stage-chip ${isActive ? 'workflow-stage-chip-active' : completedCount > 0 || !sessionData.started ? 'completed' : 'upcoming'}`}
              >
                <span className="workflow-stage-chip-label">STEP {index + 1}</span>
                <span className="workflow-stage-chip-title">{step.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        <div className="theme-card rounded-2xl p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="theme-text-primary text-sm font-bold">学习进度</div>
              <div className="theme-text-secondary mt-1 text-xs">
                已完成 {completedCount} / {totalQuestions} 轮
              </div>
            </div>
            <span className="rounded-full bg-pixiu/10 px-2.5 py-1 text-[11px] font-semibold text-pixiu">
              {progressPercent}%
            </span>
          </div>

          <div className="theme-card-soft h-3 overflow-hidden rounded-full">
            <div className="h-full rounded-full bg-pixiu transition-all duration-300" style={{ width: `${progressPercent}%` }} />
          </div>
        </div>

        <div className="theme-card rounded-2xl p-5">
          <div className="theme-text-primary mb-3 text-sm font-bold">阅读起点</div>
          <textarea
            value={sessionData.readingProgress || ''}
            onChange={(event) => onReadingProgressChange?.(event.target.value)}
            rows={4}
            disabled={isLoading || sessionData.started}
            className="theme-input w-full rounded-xl p-3 text-sm outline-none"
            placeholder="例如：我已经看完摘要和引言，接下来准备重点看方法与实验部分。"
          />

          <div className="mt-4 flex flex-wrap items-center gap-3">
            {!sessionData.started && (
              <button
                type="button"
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
                type="button"
                onClick={onRestart}
                disabled={isLoading}
                className="theme-button-secondary flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RotateCcw size={16} />
                重新开始
              </button>
            )}

          </div>

          {localError && (
            <div className="mt-4 rounded-lg border border-red-400/20 bg-red-500/10 px-3 py-2 text-xs text-red-500">
              {localError}
            </div>
          )}
        </div>

        {sessionData.intro && (
          <div className="theme-card rounded-2xl p-5">
            <div className="theme-text-primary mb-3 text-sm font-bold">本轮导语</div>
            <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
              {sessionData.intro}
            </MarkdownContent>
          </div>
        )}

        <div className="theme-card rounded-2xl p-5">
          <div className="mb-3 flex items-center gap-2">
            <CheckCircle2 size={16} className="text-pixiu" />
            <div className="theme-text-primary text-sm font-bold">问题回合</div>
          </div>

          {sessionData.started && <div className="space-y-3">{cards}</div>}
        </div>

        <div className="theme-card rounded-2xl p-5">
          <div className="theme-text-primary mb-3 text-sm font-bold">总结回顾</div>
          {sessionData.isComplete ? (
            <div className="space-y-4">
              <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none text-sm">
                {sessionData.finalSummary || '本轮引导学习已经完成。'}
              </MarkdownContent>

              {Array.isArray(sessionData.reviewSuggestions) && sessionData.reviewSuggestions.length > 0 && (
                <div className="theme-card-soft rounded-xl px-4 py-3">
                  <div className="theme-text-secondary mb-2 text-xs font-semibold tracking-wide">回读建议</div>
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
            <div className="theme-text-secondary text-sm">
              完成全部问题后，这里会给出整体掌握情况和回读建议。
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SocraticQuestionsPanel;
