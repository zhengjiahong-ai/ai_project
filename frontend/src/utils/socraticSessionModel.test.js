import assert from 'node:assert/strict';

import {
  NEUTRAL_TONE_CLASS,
  SOCRATIC_EVIDENCE_VERDICTS,
  SOCRATIC_MASTERY_LEVELS,
  SOCRATIC_TOTAL_QUESTIONS,
  createEmptySocraticSession,
  getEvidenceVerdictMeta,
  getMasteryToneClass,
  normalizeSocraticSession,
} from './socraticSessionModel.js';


const run = async () => {
  const emptySession = createEmptySocraticSession('paper-1');
  assert.equal(emptySession.pdfId, 'paper-1');
  assert.equal(emptySession.totalQuestions, SOCRATIC_TOTAL_QUESTIONS);
  assert.deepEqual(emptySession.reviewSuggestions, []);

  const legacySession = normalizeSocraticSession({
    pdfId: 'paper-legacy',
    started: true,
    readingProgress: '已读摘要',
    intro: 'intro',
    currentIndex: 2,
    currentQuestion: '第二题',
    turns: [
      {
        index: 1,
        question: '第一题',
        answer: '回答',
        masteryLevel: '较好',
        feedback: '反馈',
        hint: '提示',
      },
    ],
  });
  assert.equal(legacySession.pdfId, 'paper-legacy');
  assert.equal(legacySession.turns[0].masteryLevel, '较好');
  assert.deepEqual(legacySession.turns[0].coveredAspects, []);
  assert.deepEqual(legacySession.turns[0].missingAspects, []);
  assert.deepEqual(legacySession.turns[0].evidenceQuality, {});
  assert.deepEqual(legacySession.reviewSuggestions, []);

  const extendedSession = normalizeSocraticSession({
    pdfId: 'paper-2',
    started: true,
    totalQuestions: 5,
    currentIndex: 5,
    turns: [
      {
        index: 4,
        question: '实验题',
        answer: '我提到了实验设置。',
        masteryLevel: '一般',
        feedback: '还缺指标。',
        hint: '补上指标。',
        coveredAspects: ['实验设置'],
        missingAspects: ['评价指标', '对比结果'],
        evidenceQuality: {
          verdict: 'AMBIGUOUS',
          confidence: 0.64,
          reason: '证据只部分覆盖实验结果。',
        },
      },
    ],
    finalSummary: '总结',
    reviewSuggestions: ['建议回读“Results”部分，重点对照评价指标。'],
    isComplete: true,
  });
  assert.equal(extendedSession.isComplete, true);
  assert.equal(extendedSession.currentQuestion, '');
  assert.deepEqual(extendedSession.turns[0].coveredAspects, ['实验设置']);
  assert.deepEqual(extendedSession.turns[0].missingAspects, ['评价指标', '对比结果']);
  assert.deepEqual(extendedSession.turns[0].evidenceQuality, {
    verdict: 'AMBIGUOUS',
    confidence: 0.64,
    reason: '证据只部分覆盖实验结果。',
  });
  assert.deepEqual(extendedSession.reviewSuggestions, ['建议回读“Results”部分，重点对照评价指标。']);

  const sparseSession = normalizeSocraticSession({
    pdfId: 'paper-3',
    turns: [
      {
        question: '第一题',
        answer: '回答',
        coveredAspects: [null, '研究问题', '研究问题', ''],
        missingAspects: ['研究价值', '  ', '研究价值'],
        evidenceQuality: { verdict: 'CORRECT', confidence: '0.82' },
      },
    ],
    reviewSuggestions: ['建议回读方法部分。', '', '建议回读方法部分。'],
  });
  assert.deepEqual(sparseSession.turns[0].coveredAspects, ['研究问题']);
  assert.deepEqual(sparseSession.turns[0].missingAspects, ['研究价值']);
  assert.deepEqual(sparseSession.turns[0].evidenceQuality, { verdict: 'CORRECT', confidence: 0.82 });
  assert.deepEqual(sparseSession.reviewSuggestions, ['建议回读方法部分。']);

  // 前后端档位契约：后端 socratic_service.SOCRATIC_MASTERY_LEVELS = (需加强, 一般, 较好)。
  // 这张表漂移过（旧版缺 '需加强'、却多了后端从不下发的 '很好'），所以逐档钉住。
  assert.deepEqual(SOCRATIC_MASTERY_LEVELS, ['需加强', '一般', '较好']);
  assert.deepEqual(SOCRATIC_EVIDENCE_VERDICTS, ['CORRECT', 'AMBIGUOUS', 'INCORRECT']);
  SOCRATIC_MASTERY_LEVELS.forEach((level) => {
    const tone = getMasteryToneClass(level);
    assert.ok(tone && tone !== NEUTRAL_TONE_CLASS, `掌握度 ${level} 回落到中性色，警示色丢了`);
  });
  // '需加强' 必须是警示色，这正是旧表整档缺失的那一个。
  assert.ok(getMasteryToneClass('需加强').includes('rose'));
  // 后端从不下发 '很好'；未知档位必须安全兜底而不是抛错。
  assert.equal(getMasteryToneClass('很好'), NEUTRAL_TONE_CLASS);
  assert.equal(getMasteryToneClass(undefined), NEUTRAL_TONE_CLASS);
  SOCRATIC_EVIDENCE_VERDICTS.forEach((verdict) => {
    const meta = getEvidenceVerdictMeta(verdict);
    assert.ok(meta.label && meta.label !== '证据判断', `verdict ${verdict} 缺中文标签`);
    assert.ok(meta.toneClass && meta.toneClass !== NEUTRAL_TONE_CLASS, `verdict ${verdict} 缺配色`);
  });
  // 小写输入也要能命中：后端下发大写，但本地存储回放可能变形。
  assert.equal(getEvidenceVerdictMeta('correct').label, '证据充足');
  assert.deepEqual(getEvidenceVerdictMeta('UNKNOWN'), { label: '证据判断', toneClass: NEUTRAL_TONE_CLASS });

  console.log('socratic session model smoke tests passed');
};


run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
