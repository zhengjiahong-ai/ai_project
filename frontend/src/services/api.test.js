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

  console.log('frontend api smoke tests passed');
};


run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
