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

  await translationService.translatePage('paper-1', 3, 'Source text', { abstract: 'summary' });
  assert.equal(translateUrl, '/translate-page');
  assert.deepEqual(translatePayload, {
    pdfId: 'paper-1',
    pageIndex: 3,
    pageText: 'Source text',
    paperSkeleton: { abstract: 'summary' },
  });
  assert.equal(translateConfig.timeout, 90000);
  assert.ok(translateConfig.signal);

  console.log('frontend api smoke tests passed');
};


run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
