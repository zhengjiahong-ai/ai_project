import assert from 'node:assert/strict';

import {
  SOCRATIC_TOTAL_QUESTIONS,
  createEmptySocraticSession,
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

  console.log('socratic session model smoke tests passed');
};


run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
