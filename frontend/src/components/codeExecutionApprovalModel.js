export const canReviewExecution = (job) =>
  job?.status === 'awaiting_approval' && job?.approval?.decision === 'pending';

export const canReviewPublication = (job) =>
  job?.status === 'succeeded'
  && job?.executionResult?.status === 'succeeded'
  && job?.publicationApproval?.decision === 'pending'
  && Boolean(job?.publicationDigest);

export const groupCodeExecutionJobs = (jobs = []) => {
  const list = Array.isArray(jobs) ? jobs : [];
  return [
    { key: 'execution', label: '待执行审批', jobs: list.filter(canReviewExecution) },
    { key: 'publication', label: '待发布审批', jobs: list.filter(canReviewPublication) },
    { key: 'finished', label: '已结束', jobs: list.filter((job) => !canReviewExecution(job) && !canReviewPublication(job)) },
  ];
};

export const shortDigest = (value) => value ? `${value.slice(0, 12)}…${value.slice(-8)}` : '—';
