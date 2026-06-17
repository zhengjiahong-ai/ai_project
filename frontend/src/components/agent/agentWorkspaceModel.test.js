import assert from 'node:assert/strict';

import {
  addSelectedAgentPaperId,
  buildAgentProjectPayload,
  createEmptyAgentWorkspaceState,
  resolveNextAgentProjectNumber,
  removeSelectedAgentPaperId,
  removeAgentProjectFromState,
  resolveInitialAgentPaperSelection,
} from './agentWorkspaceModel.js';

const projects = [
  { projectId: 'project-5', title: 'Agent 项目 5' },
  { projectId: 'project-4', title: 'Agent 项目 4' },
  { projectId: 'project-3', title: 'Agent 项目 3' },
  { projectId: 'project-1', title: 'Agent 项目 1' },
];

assert.equal(resolveNextAgentProjectNumber(projects), 6);
assert.equal(resolveNextAgentProjectNumber(projects, 8), 8);
assert.equal(resolveNextAgentProjectNumber(projects, 2), 6);
assert.equal(resolveNextAgentProjectNumber([{ projectId: 'custom', title: '自定义项目' }]), 2);

const libraryPapers = [
  { id: 'paper-1', title: '第一篇论文' },
  { id: 'paper-2', title: '第二篇论文' },
  { id: 'paper-3', title: '第三篇论文' },
];

assert.deepEqual(resolveInitialAgentPaperSelection(libraryPapers, 'paper-2'), ['paper-2']);
assert.deepEqual(resolveInitialAgentPaperSelection(libraryPapers, 'missing-paper'), []);
assert.deepEqual(resolveInitialAgentPaperSelection(libraryPapers, ''), []);

assert.deepEqual(addSelectedAgentPaperId(['paper-1'], 'paper-2'), ['paper-1', 'paper-2']);
assert.deepEqual(addSelectedAgentPaperId(['paper-1'], 'paper-1'), ['paper-1']);
assert.deepEqual(addSelectedAgentPaperId(['paper-1'], '  '), ['paper-1']);

assert.deepEqual(removeSelectedAgentPaperId(['paper-1', 'paper-2'], 'paper-1'), ['paper-2']);
assert.deepEqual(removeSelectedAgentPaperId(['paper-1', 'paper-2'], 'missing-paper'), ['paper-1', 'paper-2']);

assert.deepEqual(buildAgentProjectPayload({
  projectTitle: ' Agent 项目 ',
  fallbackTitle: 'Agent 项目 8',
  projectGoal: ' 比较方法 ',
  selectedPaperIds: ['paper-1', 'paper-2'],
}), {
  title: 'Agent 项目',
  goal: '比较方法',
  paperIds: ['paper-1', 'paper-2'],
});

assert.deepEqual(buildAgentProjectPayload({
  projectTitle: '',
  fallbackTitle: 'Agent 项目 8',
  projectGoal: '',
  selectedPaperIds: ['paper-1'],
}), {
  title: 'Agent 项目 8',
  goal: '',
  paperIds: ['paper-1'],
});

const state = {
  ...createEmptyAgentWorkspaceState(),
  projects,
  activeProjectId: 'project-5',
  activeProject: projects[0],
  currentTask: { taskId: 'task-5', projectId: 'project-5' },
  latestTask: { taskId: 'task-5', projectId: 'project-5' },
  tasksByProjectId: {
    'project-5': [{ taskId: 'task-5', projectId: 'project-5' }],
    'project-4': [{ taskId: 'task-4', projectId: 'project-4' }],
  },
  nextProjectNumber: 6,
};

const nextState = removeAgentProjectFromState(state, 'project-5');

assert.deepEqual(nextState.projects.map((project) => project.projectId), ['project-4', 'project-3', 'project-1']);
assert.equal(nextState.activeProjectId, 'project-4');
assert.equal(nextState.activeProject.projectId, 'project-4');
assert.equal(nextState.currentTask.taskId, 'task-4');
assert.equal(nextState.latestTask.taskId, 'task-4');
assert.equal(nextState.tasksByProjectId['project-5'], undefined);
assert.equal(nextState.nextProjectNumber, 6);

const emptyState = removeAgentProjectFromState(
  {
    ...createEmptyAgentWorkspaceState(),
    projects: [{ projectId: 'only-project', title: 'Agent 项目 1' }],
    activeProjectId: 'only-project',
    activeProject: { projectId: 'only-project', title: 'Agent 项目 1' },
    currentTask: { taskId: 'task-1', projectId: 'only-project' },
    latestTask: { taskId: 'task-1', projectId: 'only-project' },
    tasksByProjectId: {
      'only-project': [{ taskId: 'task-1', projectId: 'only-project' }],
    },
    nextProjectNumber: 2,
  },
  'only-project',
);

assert.deepEqual(emptyState.projects, []);
assert.equal(emptyState.activeProjectId, '');
assert.equal(emptyState.activeProject, null);
assert.equal(emptyState.currentTask, null);
assert.equal(emptyState.latestTask, null);
assert.deepEqual(emptyState.tasksByProjectId, {});
assert.equal(emptyState.nextProjectNumber, 2);

console.log('agentWorkspaceModel tests passed');
