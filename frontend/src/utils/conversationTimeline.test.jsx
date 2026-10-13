import { expect, it } from 'vitest';
import { conversationTimeline } from './conversationTimeline';

it('keeps late answers at their submission position without mutating stored messages', () => {
  const task = { id: 't', messages: [
    { id: 'b:u', role: 'user', content: 'B', sourceRequestId: 'b' },
    { id: 'b:a', role: 'ai', content: 'answer B', sourceRequestId: 'b' },
    { id: 'a:u', role: 'user', content: 'A', sourceRequestId: 'a' },
    { id: 'a:a', role: 'ai', content: 'answer A', sourceRequestId: 'a' },
  ] };
  const records = { a: { taskId: 't', requestId: 'a', createdAt: '2026-10-10T01:00:00Z', status: 'succeeded' },
    b: { taskId: 't', requestId: 'b', createdAt: '2026-10-10T01:01:00Z', status: 'succeeded' } };
  expect(conversationTimeline(task, records).map(message => message.id)).toEqual(['a:user', 'a:a', 'b:user', 'b:a']);
  expect(task.messages[0].id).toBe('b:u');
});
it('anchors unfinished research and failed requests once, keeping unrelated tasks out', () => {
  const task = { id: 't', messages: [], researchRuns: [{ researchId: 'r', requestId: 'start', question: '研究问题', createdAt: '2026-10-10T01:00:00Z' }] };
  const records = { start: { taskId: 't', requestId: 'start', kind: 'research.start', status: 'succeeded' },
    failed: { taskId: 't', requestId: 'f', request: { message: '失败的问题' }, createdAt: '2026-10-10T01:01:00Z', status: 'failed' },
    other: { taskId: 'other', requestId: 'x', status: 'running' } };
  const timeline = conversationTimeline(task, records);
  expect(timeline.map(message => message.content)).toEqual(['研究问题', '失败的问题']);
  expect(timeline[0].timelineResearchId).toBe('r');
  expect(timeline[0].sourceRequestId).toBe('start');
  expect(timeline[1].timelineOperationId).toBe('f');
});
it('preserves the original question anchor and submission order through retry and completion', () => {
  const task = { id:'t', messages:[{id:'other',role:'user',content:'较晚的问题',timestamp:2000}] };
  const records={original:{taskId:'t',requestId:'original',status:'failed',createdAt:1000,request:{message:'原问题'},retriedBy:'retry'},
    retry:{taskId:'t',requestId:'retry',retryOf:'original',status:'running',createdAt:3000,request:{message:'原问题'}}};
  const pending=conversationTimeline(task,records);
  expect(pending.map(message=>message.id)).toEqual(['original:user','other']);
  records.retry.status='succeeded';
  task.messages.push({id:'retry:user',role:'user',content:'原问题',sourceRequestId:'retry'},
    {id:'retry:ai',role:'ai',content:'恢复后的回答',sourceRequestId:'retry'});
  const completed=conversationTimeline(task,records);
  expect(completed.map(message=>message.id)).toEqual(['original:user','retry:ai','other']);
  expect(completed[0].timelineRequestIds).toEqual(['original','retry']);
  expect(completed[0].originalIndex).toBe(1);
});
