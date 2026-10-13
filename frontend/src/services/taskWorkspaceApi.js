import apiClient from './api';

/** Uses the shared Java /api client, including its response-data interceptor. */
export const createTaskWorkspaceApi = (client = apiClient) => ({
  listTasks: () => client.get('/task-workspaces', { timeout: 15000, skipErrorLog: true }),
  getTask: (id) => client.get(`/task-workspaces/${encodeURIComponent(id)}`, { timeout: 15000, skipErrorLog: true }),
  identifyDocuments: (id, revision) => client.post(`/task-workspaces/${encodeURIComponent(id)}/documents/identify`, { revision }, { timeout: 15000, skipErrorLog: true }),
  moveDocument: (id, input) => client.post(`/task-workspaces/${encodeURIComponent(id)}/documents/move`, input, { timeout: 15000, skipErrorLog: true }),
  getDocumentMove: (id, requestId) => client.get(`/task-workspaces/${encodeURIComponent(id)}/documents/moves/${encodeURIComponent(requestId)}`, { timeout: 15000, skipErrorLog: true }),
  createTask: (task) => client.post('/task-workspaces', task, { timeout: 15000, skipErrorLog: true }),
  saveTask: (task) => client.put(`/task-workspaces/${encodeURIComponent(task.id)}`, task, { timeout: 15000, skipErrorLog: true }),
  startLearning: (id, input) => client.post(`/task-workspaces/${encodeURIComponent(id)}/learning/start`, input, { timeout: 180000 }),
  learningAction: (id, input) => client.post(`/task-workspaces/${encodeURIComponent(id)}/learning/action`, input, { timeout: 180000 }),
  startOperation: (id, request) => client.post(`/task-workspaces/${encodeURIComponent(id)}/operations`, request, { timeout: 15000, skipErrorLog: true }),
  listOperations: (id) => client.get(`/task-workspaces/${encodeURIComponent(id)}/operations`, { timeout: 15000, skipErrorLog: true }),
  getOperation: (id, requestId) => client.get(`/task-workspaces/${encodeURIComponent(id)}/operations/${encodeURIComponent(requestId)}`, { timeout: 15000, skipErrorLog: true }),
  cancelOperation: (id, requestId, intent = {}) => client.post(`/task-workspaces/${encodeURIComponent(id)}/operations/${encodeURIComponent(requestId)}/cancel`, intent, { timeout: 15000, skipErrorLog: true }),
  retryOperation: (id, requestId) => client.post(`/task-workspaces/${encodeURIComponent(id)}/operations/${encodeURIComponent(requestId)}/retry`, {}, { timeout: 15000, skipErrorLog: true }),
  recoverOperationResult: (id, requestId) => client.post(`/task-workspaces/${encodeURIComponent(id)}/operations/${encodeURIComponent(requestId)}/recover-result`, {}, { timeout: 15000, skipErrorLog: true }),
  listMaterials: (id) => client.get(`/task-workspaces/${encodeURIComponent(id)}/materials`, { timeout: 15000, skipErrorLog: true }),
  getMaterialFile: (id, paperId) => client.get(`/task-workspaces/${encodeURIComponent(id)}/materials/${encodeURIComponent(paperId)}/file`, { responseType: 'blob', timeout: 60000, skipErrorLog: true }),
  getMaterialAnalysis: (id, paperId) => client.get(`/task-workspaces/${encodeURIComponent(id)}/materials/${encodeURIComponent(paperId)}/analysis`, { timeout: 15000, skipErrorLog: true }),
  getMaterialProcessing: (id, paperId) => client.get(`/task-workspaces/${encodeURIComponent(id)}/materials/${encodeURIComponent(paperId)}/processing`, { timeout: 15000, skipErrorLog: true }),
  retryMaterialParse: (id, paperId) => client.post(`/task-workspaces/${encodeURIComponent(id)}/materials/${encodeURIComponent(paperId)}/parse`, {}, { timeout: 15000, skipErrorLog: true }),
  generateMaterialOverview: (id, paperId) => client.post(`/task-workspaces/${encodeURIComponent(id)}/materials/${encodeURIComponent(paperId)}/overview`, {}, { timeout: 15000, skipErrorLog: true }),
  importMaterialCache: (id, paperId, blob, filename, analysis) => {
    const body = new FormData();
    body.append('file', blob, filename);
    body.append('analysis', JSON.stringify(analysis));
    return client.put(`/task-workspaces/${encodeURIComponent(id)}/materials/${encodeURIComponent(paperId)}/cache`, body, { timeout: 60000, skipErrorLog: true });
  },
});

export const taskWorkspaceApi = createTaskWorkspaceApi();
