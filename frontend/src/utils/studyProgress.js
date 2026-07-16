import { TERMINAL_RESEARCH_STATUSES } from '../components/deepResearchPanelModel.ts';

const SURVEY_MAX = 35;
const ANALYSIS_MAX = 40;
const SYNTHESIS_MAX = 25;
const TOTAL_MAX = SURVEY_MAX + ANALYSIS_MAX + SYNTHESIS_MAX;

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

const toFiniteNumber = (value, fallback = 0) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
};

const ratioFromCount = (count, target) => {
  if (!target || target <= 0) {
    return 0;
  }
  return clamp(toFiniteNumber(count) / target, 0, 1);
};

export const calculateReadingProgress = ({ pageIndex = 0, totalPages = 0 } = {}) =>
  totalPages ? Math.min(100, Math.round(((pageIndex + 1) / totalPages) * 100)) : 0;

const countTranslatedPages = (translationState) =>
  Object.values(translationState?.pages || {}).filter(
    (page) => page?.translatedText || (Array.isArray(page?.translatedBlocks) && page.translatedBlocks.length > 0),
  ).length;

const countUserMessages = (messages = []) => messages.filter((message) => message?.role === 'user').length;

const resolveSocraticRatio = (socraticSession) => {
  if (!socraticSession?.started && !socraticSession?.isComplete && !(socraticSession?.turns || []).length) {
    return 0;
  }

  if (socraticSession?.isComplete) {
    return 1;
  }

  const turnsCount = Array.isArray(socraticSession?.turns) ? socraticSession.turns.length : 0;
  const totalQuestions = Math.max(1, toFiniteNumber(socraticSession?.totalQuestions, 5));
  return clamp(0.3 + ratioFromCount(turnsCount, totalQuestions) * 0.7, 0, 0.95);
};

const resolveResearchRatio = (deepResearchState) => {
  const task = deepResearchState?.task || null;
  const progress = clamp(toFiniteNumber(task?.progress, 0), 0, 1);
  const findingsCount = Array.isArray(task?.findings) ? task.findings.length : 0;
  const hasReport = Boolean(`${task?.report || ''}`.trim());
  const status = `${task?.status || ''}`.trim().toLowerCase();
  const terminalSuccess = status === 'succeeded';
  const researchStarted = Boolean(
    task?.taskId || `${deepResearchState?.questionDraft || ''}`.trim() || deepResearchState?.briefPreview,
  );

  if (!researchStarted) {
    return 0;
  }

  const base = 0.2;
  const progressContribution = progress * 0.35;
  const findingsContribution = ratioFromCount(findingsCount, 3) * 0.25;
  const completionContribution = terminalSuccess || hasReport ? 0.2 : 0;
  const terminalPenalty =
    TERMINAL_RESEARCH_STATUSES.includes(status) && !terminalSuccess && !hasReport ? -0.1 : 0;

  return clamp(base + progressContribution + findingsContribution + completionContribution + terminalPenalty, 0.15, 1);
};

const resolveStudyPhase = ({ surveyScore, analysisScore, synthesisScore, hasDeconstruct, hasAnySignal, totalScore }) => {
  if (!hasAnySignal) {
    return '待开始';
  }

  if (totalScore >= 85 && analysisScore >= 24 && synthesisScore >= 12) {
    return '闭环完成';
  }

  if (synthesisScore >= 10) {
    return '沉淀中';
  }

  if (analysisScore >= 14) {
    return '精读中';
  }

  if (hasDeconstruct || surveyScore >= 10) {
    return '浅读中';
  }

  return '已开始';
};

const resolveStudySummary = ({
  hasDeconstruct,
  pageCoverage,
  translatedPageCount,
  userMessageCount,
  hasBackgroundKnowledge,
  hasAnalysis,
  socraticStarted,
  researchStarted,
  noteCount,
  highlightCount,
  artifactCount,
  totalScore,
}) => {
  const hasAnalysisFlow = hasBackgroundKnowledge || hasAnalysis || socraticStarted || researchStarted;
  const hasSynthesis = noteCount > 0 || highlightCount > 0 || artifactCount > 0;

  if (!hasDeconstruct && pageCoverage === 0 && userMessageCount === 0 && translatedPageCount === 0) {
    return '已入库，尚未开始正式研读。';
  }

  if (!hasDeconstruct) {
    return '已开始浏览正文，但尚未完成篇章解构。';
  }

  if (!hasAnalysisFlow) {
    if (userMessageCount > 0 || translatedPageCount > 0 || pageCoverage >= 25) {
      return '已完成浅读，建议进入补课、批判或引导学习。';
    }
    return '已完成篇章解构，建议先用问答或翻译进入正文。';
  }

  if (!hasSynthesis) {
    return '已进入深度探究，下一步适合沉淀笔记或工作台卡片。';
  }

  if (totalScore >= 85) {
    return '已形成从阅读、探究到沉淀的较完整闭环。';
  }

  return '已开始形成个人知识资产，仍可继续补充证据链与结论沉淀。';
};

export const buildStudyProgressSnapshot = ({
  pdfId = null,
  pdfPageState = {},
  deconstructData = null,
  analysisData = null,
  backgroundKnowledgeData = null,
  socraticSession = null,
  translationState = null,
  messages = [],
  notes = [],
  pdfHighlights = [],
  workbenchCards = [],
  deepResearchState = null,
} = {}) => {
  const pageCoverage = calculateReadingProgress(pdfPageState);
  const translatedPageCount = countTranslatedPages(translationState);
  const userMessageCount = countUserMessages(messages);
  const noteCount = Array.isArray(notes) ? notes.length : 0;
  const highlightCount = Array.isArray(pdfHighlights) ? pdfHighlights.length : 0;
  const artifactCount = Array.isArray(workbenchCards) ? workbenchCards.length : 0;

  const hasDeconstruct = Boolean(
    deconstructData?.paper_skeleton ||
      deconstructData?.paper_structure ||
      (Array.isArray(deconstructData?.paper_structure?.sections) && deconstructData.paper_structure.sections.length > 0),
  );
  const hasAnalysis = Boolean(analysisData && typeof analysisData === 'object' && Object.keys(analysisData).length > 0);
  const hasBackgroundKnowledge = Boolean(
    backgroundKnowledgeData &&
      typeof backgroundKnowledgeData === 'object' &&
      Object.keys(backgroundKnowledgeData).length > 0,
  );
  const socraticStarted = Boolean(
    socraticSession?.started || socraticSession?.isComplete || (socraticSession?.turns || []).length > 0,
  );
  const researchStarted = Boolean(
    deepResearchState?.task?.taskId ||
      `${deepResearchState?.questionDraft || ''}`.trim() ||
      deepResearchState?.briefPreview,
  );

  const surveyScore = Math.round(
    pageCoverage * 0.2 +
      (hasDeconstruct ? 10 : 0) +
      ratioFromCount(translatedPageCount, Math.max(2, Math.min(5, toFiniteNumber(pdfPageState?.totalPages, 0) || 3))) * 5,
  );
  const analysisScore = Math.round(
    ratioFromCount(userMessageCount, 3) * 8 +
      (hasBackgroundKnowledge ? 8 : 0) +
      (hasAnalysis ? 10 : 0) +
      resolveSocraticRatio(socraticSession) * 6 +
      resolveResearchRatio(deepResearchState) * 8,
  );
  const synthesisScore = Math.round(
    ratioFromCount(noteCount, 3) * 10 +
      ratioFromCount(highlightCount, 4) * 5 +
      ratioFromCount(artifactCount, 3) * 10,
  );

  const totalScore = clamp(surveyScore + analysisScore + synthesisScore, 0, TOTAL_MAX);
  const hasAnySignal =
    totalScore > 0 ||
    hasDeconstruct ||
    userMessageCount > 0 ||
    translatedPageCount > 0 ||
    noteCount > 0 ||
    highlightCount > 0 ||
    artifactCount > 0;

  const phase = resolveStudyPhase({
    surveyScore,
    analysisScore,
    synthesisScore,
    hasDeconstruct,
    hasAnySignal,
    totalScore,
  });
  const summary = resolveStudySummary({
    hasDeconstruct,
    pageCoverage,
    translatedPageCount,
    userMessageCount,
    hasBackgroundKnowledge,
    hasAnalysis,
    socraticStarted,
    researchStarted,
    noteCount,
    highlightCount,
    artifactCount,
    totalScore,
  });

  return {
    pdfId,
    readingProgress: pageCoverage,
    currentPage: toFiniteNumber(pdfPageState?.totalPages, 0) ? toFiniteNumber(pdfPageState?.pageIndex, 0) + 1 : 0,
    totalPages: toFiniteNumber(pdfPageState?.totalPages, 0),
    studyProgress: totalScore,
    studyPhase: phase,
    studySummary: summary,
    progressSignals: {
      pageCoverage,
      translatedPageCount,
      userMessageCount,
      noteCount,
      highlightCount,
      artifactCount,
      hasDeconstruct,
      hasAnalysis,
      hasBackgroundKnowledge,
      socraticStarted,
      socraticCompleted: Boolean(socraticSession?.isComplete),
      socraticTurnCount: Array.isArray(socraticSession?.turns) ? socraticSession.turns.length : 0,
      researchStarted,
      researchStatus: deepResearchState?.task?.status || '',
      researchFindingCount: Array.isArray(deepResearchState?.task?.findings) ? deepResearchState.task.findings.length : 0,
      axes: {
        survey: Math.round((surveyScore / SURVEY_MAX) * 100),
        analysis: Math.round((analysisScore / ANALYSIS_MAX) * 100),
        synthesis: Math.round((synthesisScore / SYNTHESIS_MAX) * 100),
      },
    },
  };
};

export const getPaperStudyProgress = (paper, currentSnapshot = null) => {
  const source = currentSnapshot && paper?.id === currentSnapshot?.pdfId ? currentSnapshot : paper || {};
  const fallbackReading = clamp(toFiniteNumber(source.readingProgress, 0), 0, 100);
  const studyProgress = Number.isFinite(Number(source.studyProgress))
    ? clamp(Number(source.studyProgress), 0, 100)
    : fallbackReading;
  const pageCoverage = Number.isFinite(Number(source?.progressSignals?.pageCoverage))
    ? clamp(Number(source.progressSignals.pageCoverage), 0, 100)
    : fallbackReading;
  const axes = source?.progressSignals?.axes || {};

  return {
    studyProgress,
    studyPhase: `${source.studyPhase || ''}`.trim() || (studyProgress > 0 ? '进行中' : '待开始'),
    studySummary:
      `${source.studySummary || ''}`.trim() ||
      (studyProgress > 0 ? '当前为旧版记录，完成度暂按页码位置估算。' : '已入库，尚未开始正式研读。'),
    pageCoverage,
    currentPage: toFiniteNumber(source.currentPage, 0),
    totalPages: toFiniteNumber(source.totalPages, 0),
    axes: {
      survey: clamp(toFiniteNumber(axes.survey, pageCoverage), 0, 100),
      analysis: clamp(toFiniteNumber(axes.analysis, 0), 0, 100),
      synthesis: clamp(toFiniteNumber(axes.synthesis, 0), 0, 100),
    },
  };
};
