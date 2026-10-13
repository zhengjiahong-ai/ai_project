import client from './api';

const path = (taskId, researchId = '') => `/task-workspaces/${encodeURIComponent(taskId)}/research${researchId ? `/${encodeURIComponent(researchId)}` : ''}`;
export const taskResearchApi = {
  start: (taskId, input) => client.post(`${path(taskId)}/start`, input),
  get: (taskId, researchId) => client.get(path(taskId, researchId)),
  action: (taskId, researchId, action, input = {}) => client.post(`${path(taskId, researchId)}/${action}`, input),
  capabilities: (taskId) => client.get(`/task-workspaces/${encodeURIComponent(taskId)}/research/capabilities`),
  addSource: (taskId, runId, sourceId, input) => client.post(
    `${path(taskId, runId)}/sources/${encodeURIComponent(sourceId)}/add`, input),
};
