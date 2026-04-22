export const SOCRATIC_TOTAL_QUESTIONS = 5;

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
