import { beforeEach, expect, it } from 'vitest';
import { clearResearchIntent, getResearchIntent, researchIntentKey } from './researchStartIntent';

beforeEach(() => sessionStorage.clear());

it('keeps the original payload and nonce after reload and task revision changes', () => {
  const input = { question: '比较结果', expectedTaskRevision: 3, materialSelection: { materialIds: ['a'] } };
  const key = researchIntentKey('t', input);
  const first = getResearchIntent(key, input);
  const updated = { ...input, expectedTaskRevision: 4 };
  const restored = getResearchIntent(researchIntentKey('t', updated), updated);
  expect(restored).toEqual(first);
  expect(restored.input.expectedTaskRevision).toBe(3);
});

it('a confirmed creation clears the pending intent', () => {
  const input = { question: '比较结果' };
  const key = researchIntentKey('t', input);
  const first = getResearchIntent(key, input);
  clearResearchIntent(key);
  expect(getResearchIntent(key, input).requestId).not.toBe(first.requestId);
});

it('changed materials and questions use separate intents', () => {
  expect(researchIntentKey('t', { question: 'a' })).not.toBe(researchIntentKey('t', { question: 'b' }));
  expect(researchIntentKey('t', { materialIds: ['a'] })).not.toBe(researchIntentKey('t', { materialIds: ['b'] }));
});
