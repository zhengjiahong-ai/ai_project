import assert from 'node:assert/strict';

import {
  buildReadingWorkflowSuggestions,
  getPrimaryReadingWorkflowSuggestion,
} from './readingWorkflowModel.ts';

const findSuggestion = (suggestions, actionType) => suggestions.find((item) => item.action?.type === actionType);

const noPdfSuggestions = buildReadingWorkflowSuggestions({
  hasPdf: false,
  activeTab: 'chat',
  pdfId: '',
});

assert.equal(noPdfSuggestions.length, 1);
assert.equal(noPdfSuggestions[0].title, '先上传一篇论文');
assert.equal(findSuggestion(noPdfSuggestions, 'agent'), undefined);

const deconstructingSuggestions = buildReadingWorkflowSuggestions({
  hasPdf: true,
  isDeconstructing: true,
  activeTab: 'chat',
  pdfId: 'paper-1',
});

assert.deepEqual(deconstructingSuggestions.map((item) => item.action?.tabId), ['deconstruct', 'chat']);

const chatSuggestions = buildReadingWorkflowSuggestions({
  hasPdf: true,
  activeTab: 'chat',
  latestUserMessage: { content: '这个方法为什么有效？' },
  pdfId: 'paper-1',
});

assert.equal(chatSuggestions.length, 3);
assert.equal(chatSuggestions[0].action.type, 'tab');
assert.equal(chatSuggestions[0].action.tabId, 'background');
assert.equal(chatSuggestions[1].action.tabId, 'analysis');
assert.deepEqual(findSuggestion(chatSuggestions, 'agent').action, {
  type: 'agent',
  pdfId: 'paper-1',
});

const analysisSuggestions = buildReadingWorkflowSuggestions({
  hasPdf: true,
  activeTab: 'analysis',
  pdfId: 'paper-1',
});

assert.equal(analysisSuggestions[0].action.tabId, 'deep-research');
assert.equal(analysisSuggestions[1].action.type, 'workbench');
assert.equal(analysisSuggestions[1].action.tabId, 'notes');
assert.equal(findSuggestion(analysisSuggestions, 'agent').label, '进入 Agent 比较');

const deepResearchSuggestions = buildReadingWorkflowSuggestions({
  hasPdf: true,
  activeTab: 'deep-research',
  deepResearchState: {
    task: {
      status: 'succeeded',
      findings: [{ summary: '主要发现' }],
    },
  },
  artifactCount: 2,
  pdfId: 'paper-2',
});

assert.equal(deepResearchSuggestions.length, 3);
assert.equal(deepResearchSuggestions[0].action.tabId, 'analysis');
assert.equal(deepResearchSuggestions[1].action.type, 'workbench');
assert.equal(findSuggestion(deepResearchSuggestions, 'agent').action.pdfId, 'paper-2');

const notesSuggestions = buildReadingWorkflowSuggestions({
  hasPdf: true,
  activeTab: 'notes',
  artifactCount: 4,
  pdfId: 'paper-3',
});

assert.equal(notesSuggestions.length, 3);
assert.equal(notesSuggestions[0].action.tabId, 'deconstruct');
assert.equal(notesSuggestions[1].action.tabId, 'chat');
assert.equal(findSuggestion(notesSuggestions, 'agent').title, '进入多论文研究');

assert.equal(getPrimaryReadingWorkflowSuggestion(chatSuggestions).label, '去补背景');
assert.equal(getPrimaryReadingWorkflowSuggestion(noPdfSuggestions), null);

console.log('readingWorkflowModel tests passed');
