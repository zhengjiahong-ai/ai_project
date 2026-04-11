import assert from 'node:assert/strict';

import { createApiService, resolveApiBaseUrl } from './api.js';


const run = async () => {
  assert.equal(resolveApiBaseUrl({ VITE_API_BASE_URL: 'http://example.com/api' }), 'http://example.com/api');

  let uploadCall;
  const uploadService = createApiService({
    post: async (url, body, config) => {
      uploadCall = { url, body, config };
      return { status: 'success' };
    },
    get: async () => ({}),
  });

  await uploadService.uploadPdf(new Blob(['pdf'], { type: 'application/pdf' }));
  assert.equal(uploadCall.url, '/upload');
  assert.ok(uploadCall.body instanceof FormData);
  assert.equal(uploadCall.config.headers['Content-Type'], 'multipart/form-data');

  let historyUrl = '';
  const historyService = createApiService({
    get: async (url) => {
      historyUrl = url;
      return { status: 'success' };
    },
    post: async () => ({}),
  });

  await historyService.getChatHistory('session-1');
  assert.equal(historyUrl, '/chat/history/session-1');

  let criticalReadingUrl = '';
  const criticalReadingService = createApiService({
    post: async (url) => {
      criticalReadingUrl = url;
      return { status: 'success' };
    },
    get: async () => ({}),
  });

  await criticalReadingService.criticalReading('paper-1');
  assert.equal(criticalReadingUrl, '/critical-reading/paper-1');

  let backgroundPayload = null;
  let backgroundUrl = '';
  const backgroundService = createApiService({
    post: async (url, body) => {
      backgroundUrl = url;
      backgroundPayload = body;
      return { status: 'success' };
    },
    get: async () => ({}),
  });

  await backgroundService.backgroundKnowledge({
    pdfId: 'paper-1',
    paperSkeleton: { abstract: 'summary' },
    paperStructure: { research_problem: 'RAG' },
    paper_topic: 'RAG',
    user_knowledge_level: 'normal',
  });
  assert.equal(backgroundUrl, '/background-knowledge');
  assert.deepEqual(backgroundPayload, {
    pdfId: 'paper-1',
    paperSkeleton: { abstract: 'summary' },
    paperStructure: { research_problem: 'RAG' },
    paper_topic: 'RAG',
    user_knowledge_level: 'normal',
  });

  let explainPayload = null;
  let explainUrl = '';
  const explainService = createApiService({
    post: async (url, body) => {
      explainUrl = url;
      explainPayload = body;
      return { status: 'success', explanation: '解释' };
    },
    get: async () => ({}),
  });

  await explainService.explainText('contrastive loss', 'paper-1', 4, 'This page introduces contrastive learning.');
  assert.equal(explainUrl, '/explain');
  assert.deepEqual(explainPayload, {
    text: 'contrastive loss',
    pdfId: 'paper-1',
    pageNumber: 4,
    context: 'This page introduces contrastive learning.',
  });

  let translatePayload = null;
  let translateUrl = '';
  let translateConfig = null;
  const translationService = createApiService({
    post: async (url, body, config) => {
      translateUrl = url;
      translatePayload = body;
      translateConfig = config;
      return { status: 'success' };
    },
    get: async () => ({}),
  });

  await translationService.translatePage(
    'paper-1',
    3,
    'Source text',
    { abstract: 'summary' },
    {
      viewport: { width: 600, height: 800 },
      blocks: [{ id: 'block-1', text: 'Source text', bbox: { left: 0.1, top: 0.1, width: 0.2, height: 0.1 } }],
      excludedZonesVersion: 1,
    },
  );
  assert.equal(translateUrl, '/translate-page');
  assert.deepEqual(translatePayload, {
    pdfId: 'paper-1',
    pageIndex: 3,
    pageText: 'Source text',
    paperSkeleton: { abstract: 'summary' },
    pageLayout: {
      viewport: { width: 600, height: 800 },
      blocks: [{ id: 'block-1', text: 'Source text', bbox: { left: 0.1, top: 0.1, width: 0.2, height: 0.1 } }],
      excludedZonesVersion: 1,
    },
  });
  assert.equal(translateConfig.timeout, 90000);
  assert.ok(translateConfig.signal);

  console.log('frontend api smoke tests passed');
};


run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
