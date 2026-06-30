const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

const source = { sourceId: 'council-source-1', sourceType: 'current_paper', text: '主实验支持结论，但消融结果仍存在冲突。', pageIndex: 0, sectionId: 'results', chunkIndex: 1 };
const councilResult = {
  opinions: [
    { reviewerId: 'evidence-reviewer', role: 'evidence_reviewer', provider: 'deepseek', model: 'deepseek-chat', verdict: 'supported', conclusion: '主实验支持有限结论。', reason: '引用了主实验结果。', sourceIds: [source.sourceId], confidence: 0.82, abstain: false, abstainReason: '', usage: { inputTokens: 20, outputTokens: 10, totalTokens: 30, estimated: false } },
    { reviewerId: 'contradiction-reviewer', role: 'contradiction_reviewer', provider: 'deepseek', model: 'deepseek-chat', verdict: 'abstain', conclusion: '', reason: '', sourceIds: [], confidence: 0, abstain: true, abstainReason: 'provider_unavailable', usage: { inputTokens: 0, outputTokens: 0, totalTokens: 0, estimated: true } },
  ],
  agreements: [],
  disagreements: [{ type: 'verdict_disagreement', reviewerIds: ['evidence-reviewer'], positions: [], sourceIds: [source.sourceId], reason: 'Reviewer 结论不同，需要人工核查。', highRisk: true }],
  abstentions: [{ reviewerId: 'contradiction-reviewer', role: 'contradiction_reviewer', reason: 'provider_unavailable' }],
  evidenceCoverage: { allowedSourceCount: 1, citedSourceCount: 1, sharedSourceIds: [], uncitedSourceIds: [], ratio: 1 },
  recommendedAction: 'manual_review_required',
};

const baseTask = {
  taskId: 'research-council-smoke-1', traceId: 'research-council-trace-1', question: '实验是否支持结论？', pdfId: 'paper-smoke-1',
  plan: [{ id: 'plan-1', question: '核查实验与消融结果', status: 'done' }],
  findings: [{ id: 'finding-1', subQuestion: '核查实验与消融结果', summary: '证据存在需要保留的分歧。', verdict: 'AMBIGUOUS', sourceIds: [source.sourceId], sources: [source], missingAspects: [], coverage: { score: 0.5 } }],
  conflicts: [], reviewRisks: [], report: '## Council 报告\n证据仍需人工核查。', error: '',
  humanReview: { plan: { status: 'approved' }, final: { status: 'pending' } },
  externalSearchConfig: { allowExternalSearch: false, provider: 'disabled', budget: { callLimit: 0, evidenceLimit: 0, callsUsed: 0, evidenceUsed: 0 }, status: 'disabled', degradation: '' },
  council: { allowCouncil: true, status: 'degraded', maxReviews: 3, reviewCount: 1, degradation: 'reviewer_abstained', reviews: [{ targetType: 'finding', targetId: 'finding-1', question: '实验证据是否充分？', sourceIds: [source.sourceId], reviewStatus: 'pending', result: councilResult }] },
};

export const installCouncilResearchRoute = async (page) => {
  const state = { finalReviewPayload: null, planReviewed: false };
  await page.route('http://localhost:8081/api/research-tasks**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'GET' && url.pathname === '/api/research-tasks/latest') return json(route, { status: 'success', task: { ...baseTask, status: 'awaiting_final_review', stage: 'synthesizing', progress: 0.95 } });
    if (request.method() === 'POST' && url.pathname === '/api/research-tasks') {
      return json(route, { status: 'success', task: { ...baseTask, status: 'awaiting_plan_review', stage: 'planning', progress: 0.2, findings: [], report: '', council: { ...baseTask.council, status: 'pending', reviewCount: 0, reviews: [], degradation: '' } } });
    }
    if (request.method() === 'POST' && url.pathname.endsWith('/plan-review')) {
      state.planReviewed = true;
      return json(route, { status: 'success', task: { ...baseTask, status: 'running', stage: 'retrieving', progress: 0.5 } });
    }
    if (request.method() === 'POST' && url.pathname.endsWith('/final-review')) {
      state.finalReviewPayload = request.postDataJSON();
      return json(route, { status: 'success', task: { ...baseTask, status: 'succeeded', stage: 'done', progress: 1, council: { ...baseTask.council, reviews: [{ ...baseTask.council.reviews[0], reviewStatus: state.finalReviewPayload.councilReviews[0].reviewStatus }] } } });
    }
    if (request.method() === 'GET' && url.pathname === `/api/research-tasks/${baseTask.taskId}`) {
      return json(route, { status: 'success', task: { ...baseTask, status: state.planReviewed ? 'awaiting_final_review' : 'running', stage: 'synthesizing', progress: 0.95 } });
    }
    return route.fallback();
  });
  await page.route('http://localhost:8081/api/traces/research-council-trace-1', (route) => json(route, { status: 'success', trace: { traceId: 'research-council-trace-1', taskType: 'deep_research', status: 'awaiting_review', durationMs: 200, counters: { councilCalls: 2, councilFailures: 1, councilLatencyMs: 100, councilInputTokens: 20, councilOutputTokens: 10, councilTotalTokens: 30 }, steps: [] } }));
  return state;
};
