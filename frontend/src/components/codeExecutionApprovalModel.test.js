import assert from 'node:assert/strict';

import { canReviewExecution, canReviewPublication, groupCodeExecutionJobs } from './codeExecutionApprovalModel.js';

const pending = { jobId: 'job-1', status: 'awaiting_approval', approval: { decision: 'pending' } };
const succeeded = {
  jobId: 'job-2', status: 'succeeded', publicationDigest: 'a'.repeat(64),
  publicationApproval: { decision: 'pending' }, executionResult: { status: 'succeeded' },
};

assert.equal(canReviewExecution(pending), true);
assert.equal(canReviewExecution({ ...pending, approval: { decision: 'approved' } }), false);
assert.equal(canReviewPublication(succeeded), true);
assert.equal(canReviewPublication({ ...succeeded, status: 'failed' }), false);
assert.deepEqual(groupCodeExecutionJobs([pending, succeeded]).map((group) => group.key), [
  'execution', 'publication', 'finished',
]);
assert.equal(groupCodeExecutionJobs([pending, succeeded])[0].jobs[0].jobId, 'job-1');
assert.equal(groupCodeExecutionJobs([pending, succeeded])[1].jobs[0].jobId, 'job-2');

console.log('code execution approval model tests passed');
