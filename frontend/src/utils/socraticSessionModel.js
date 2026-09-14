export const SOCRATIC_TOTAL_QUESTIONS = 5;

// 与后端 services/socratic_service.py 的 SOCRATIC_MASTERY_LEVELS 逐一对齐。
// 这张表漂移过：旧版缺 '需加强'、却留着后端从不下发的 '很好'，结果掌握度最差的
// 回合回落到中性色，把最该出现的警示色丢掉了。档位集合同步在这里导出，
// 让测试能直接钉住两边一致。
export const SOCRATIC_MASTERY_LEVELS = ['需加强', '一般', '较好'];

// 后端 evidence verdict 三档，见 services/retrieval_judge_service.py。
export const SOCRATIC_EVIDENCE_VERDICTS = ['CORRECT', 'AMBIGUOUS', 'INCORRECT'];

export const NEUTRAL_TONE_CLASS = 'theme-card-soft';

const MASTERY_TONE_MAP = {
  '需加强': 'border-rose-400/25 bg-rose-500/10 text-rose-400',
  '一般': 'border-amber-400/25 bg-amber-500/10 text-amber-500',
  '较好': 'border-emerald-400/25 bg-emerald-500/10 text-emerald-400',
};

const EVIDENCE_VERDICT_META = {
  CORRECT: { label: '证据充足', toneClass: 'border-emerald-400/25 bg-emerald-500/10 text-emerald-400' },
  AMBIGUOUS: { label: '部分相关', toneClass: 'border-amber-400/25 bg-amber-500/10 text-amber-500' },
  INCORRECT: { label: '证据不足', toneClass: 'border-rose-400/25 bg-rose-500/10 text-rose-400' },
};

export const getMasteryToneClass = (level) => MASTERY_TONE_MAP[`${level ?? ''}`.trim()] || NEUTRAL_TONE_CLASS;

export const getEvidenceVerdictMeta = (verdict) => {
  const key = `${verdict ?? ''}`.trim().toUpperCase();
  return EVIDENCE_VERDICT_META[key] || { label: '证据判断', toneClass: NEUTRAL_TONE_CLASS };
};

const normalizeStringArray = (value, limit = 5) => {
  if (!Array.isArray(value)) {
    return [];
  }

  const normalized = [];
  const seen = new Set();

  value.forEach((item) => {
    const text = `${item ?? ''}`.trim();
    if (!text) return;
    const key = text.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    normalized.push(text);
  });

  return normalized.slice(0, limit);
};

const normalizeEvidenceQuality = (value) => {
  if (!value || typeof value !== 'object') {
    return {};
  }

  const verdict = `${value.verdict ?? ''}`.trim();
  const reason = `${value.reason ?? ''}`.trim();
  const confidenceValue = Number(value.confidence);
  const normalized = {};

  if (verdict) {
    normalized.verdict = verdict;
  }
  if (Number.isFinite(confidenceValue)) {
    normalized.confidence = confidenceValue;
  }
  if (reason) {
    normalized.reason = reason;
  }

  return normalized;
};

const normalizeSocraticTurn = (turn, index) => ({
  index: Number(turn?.index) || index + 1,
  question: turn?.question || '',
  answer: turn?.answer || '',
  masteryLevel: turn?.masteryLevel || '一般',
  feedback: turn?.feedback || '',
  hint: turn?.hint || '',
  coveredAspects: normalizeStringArray(turn?.coveredAspects),
  missingAspects: normalizeStringArray(turn?.missingAspects),
  evidenceQuality: normalizeEvidenceQuality(turn?.evidenceQuality),
});

export const createEmptySocraticSession = (pdfId = null, overrides = {}) => ({
  pdfId,
  started: false,
  readingProgress: '',
  intro: '',
  totalQuestions: SOCRATIC_TOTAL_QUESTIONS,
  currentIndex: 1,
  currentQuestion: '',
  turns: [],
  finalSummary: '',
  reviewSuggestions: [],
  isComplete: false,
  updatedAt: null,
  ...overrides,
});

export const normalizeSocraticSession = (storedValue, pdfId = null) => {
  if (!storedValue) {
    return createEmptySocraticSession(pdfId);
  }

  const turns = Array.isArray(storedValue.turns)
    ? storedValue.turns
        .map((turn, index) => normalizeSocraticTurn(turn, index))
        .filter((turn) => turn.question && turn.answer)
    : [];

  const totalQuestions = Number(storedValue.totalQuestions) || SOCRATIC_TOTAL_QUESTIONS;
  const isComplete = Boolean(storedValue.isComplete);
  const inferredCurrentIndex = Math.min(turns.length + 1, totalQuestions);
  const currentIndex = isComplete
    ? totalQuestions
    : Math.max(1, Math.min(Number(storedValue.currentIndex) || inferredCurrentIndex, totalQuestions));

  return createEmptySocraticSession(pdfId ?? storedValue.pdfId ?? null, {
    started: Boolean(storedValue.started || turns.length > 0 || storedValue.currentQuestion || isComplete),
    readingProgress: storedValue.readingProgress || '',
    intro: storedValue.intro || '',
    totalQuestions,
    currentIndex,
    currentQuestion: isComplete ? '' : storedValue.currentQuestion || '',
    turns,
    finalSummary: storedValue.finalSummary || '',
    reviewSuggestions: normalizeStringArray(storedValue.reviewSuggestions, 3),
    isComplete,
    updatedAt: storedValue.updatedAt || null,
  });
};
