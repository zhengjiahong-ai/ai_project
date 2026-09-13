import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

// Mock the api service before importing the component
const mockCreateAgentRun = vi.fn();
const mockCreateAgentTaskRun = vi.fn();
const mockGetAgentTaskMessages = vi.fn();
const mockCancelAgentRun = vi.fn();
const mockRetryAgentRun = vi.fn();
const mockRunAgentGraph = vi.fn();
const mockCreateAgentTask = vi.fn();
const mockGetAgentWorkspace = vi.fn();
const mockGetAgentRun = vi.fn();
const mockGetAgentRunArtifacts = vi.fn();
const mockGetAgentRunTimeline = vi.fn();
const mockGetAgentGraphState = vi.fn();
const mockReviewAgentRunPlan = vi.fn();
const mockReviewAgentRunFinal = vi.fn();
const mockResumeAgentGraph = vi.fn();
const mockReviewAgentPlan = vi.fn();
const mockReviewAgentFinal = vi.fn();
const mockListAgentProjects = vi.fn();
const mockGetAgentProject = vi.fn();
const mockListAgentProjectTasks = vi.fn();
const mockGetAgentTask = vi.fn();
const mockCancelAgentTask = vi.fn();

vi.mock('../../services/api', () => ({
  apiService: {
    createAgentRun: (...args: unknown[]) => mockCreateAgentRun(...args),
    createAgentTaskRun: (...args: unknown[]) => mockCreateAgentTaskRun(...args),
    getAgentTaskMessages: (...args: unknown[]) => mockGetAgentTaskMessages(...args),
    cancelAgentRun: (...args: unknown[]) => mockCancelAgentRun(...args),
    retryAgentRun: (...args: unknown[]) => mockRetryAgentRun(...args),
    runAgentGraph: (...args: unknown[]) => mockRunAgentGraph(...args),
    createAgentTask: (...args: unknown[]) => mockCreateAgentTask(...args),
    getAgentWorkspace: (...args: unknown[]) => mockGetAgentWorkspace(...args),
    getAgentRun: (...args: unknown[]) => mockGetAgentRun(...args),
    getAgentRunArtifacts: (...args: unknown[]) => mockGetAgentRunArtifacts(...args),
    getAgentRunTimeline: (...args: unknown[]) => mockGetAgentRunTimeline(...args),
    getAgentGraphState: (...args: unknown[]) => mockGetAgentGraphState(...args),
    reviewAgentRunPlan: (...args: unknown[]) => mockReviewAgentRunPlan(...args),
    reviewAgentRunFinal: (...args: unknown[]) => mockReviewAgentRunFinal(...args),
    resumeAgentGraph: (...args: unknown[]) => mockResumeAgentGraph(...args),
    reviewAgentPlan: (...args: unknown[]) => mockReviewAgentPlan(...args),
    reviewAgentFinal: (...args: unknown[]) => mockReviewAgentFinal(...args),
    listAgentProjects: (...args: unknown[]) => mockListAgentProjects(...args),
    getAgentProject: (...args: unknown[]) => mockGetAgentProject(...args),
    listAgentProjectTasks: (...args: unknown[]) => mockListAgentProjectTasks(...args),
    getAgentTask: (...args: unknown[]) => mockGetAgentTask(...args),
    cancelAgentTask: (...args: unknown[]) => mockCancelAgentTask(...args),
  },
}));

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// Import component after mocks are set up
import AgentWorkspace from './AgentWorkspace.tsx';

const TEST_PROJECT_ID = 'test-project-123';
const TEST_RUN_ID = 'test-run-456';

const mockProject = {
  projectId: TEST_PROJECT_ID,
  title: 'Test Project',
  goal: 'Test goal',
  paperIds: ['paper-1'],
  papers: [],
  latestTaskId: '',
  defaultConstraints: '',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

const mockRunResponse = {
  status: 'success',
  run: {
    runId: TEST_RUN_ID,
    taskId: 'research-task-1',
    projectId: TEST_PROJECT_ID,
    traceId: 'trace-1',
    status: 'awaiting_plan_review',
    executionPhase: 'planning',
    progress: 0.2,
    prompt: 'Test research question',
    focusedPaperIds: ['paper-1'],
    constraints: '',
    context: {},
    humanReview: { plan: { status: 'pending' }, final: { status: 'pending' } },
    reviewRisks: [],
    traceSummary: {},
    externalSearchConfig: {
      allowExternalSearch: false,
      provider: 'disabled',
      budget: { callLimit: 3, evidenceLimit: 15, callsUsed: 0, evidenceUsed: 0 },
      status: 'disabled',
      degradation: '',
    },
    error: '',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  },
};

// Empty workspace response (no active run)
const mockEmptyWorkspaceResponse = {
  status: 'success',
  workspace: {
    project: mockProject,
    activeRun: null,
    pendingReview: null,
    latestArtifacts: null,
    recentRuns: [],
    timeline: [],
    uiHints: {},
  },
};

// Workspace response with active run
const mockWorkspaceResponse = {
  status: 'success',
  workspace: {
    project: mockProject,
    activeRun: mockRunResponse.run,
    pendingReview: {
      runId: TEST_RUN_ID,
      planItems: [{ id: 'retrieve', label: 'Retrieve papers' }],
    },
    latestArtifacts: null,
    recentRuns: [mockRunResponse.run],
    timeline: [],
    uiHints: {},
  },
};

describe('AgentWorkspace - Batch 1: Unified Execution Entry', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    localStorageMock.clear();

    // Set up initial localStorage state with active project but NO tasks
    localStorageMock.setItem(
      'pixiu-agent-workspace',
      JSON.stringify({
        projects: [mockProject],
        activeProjectId: TEST_PROJECT_ID,
        activeProject: mockProject,
        activeWorkspace: null,
        latestTask: null,
        currentTask: null,
        tasksByProjectId: {},
        nextProjectNumber: 2,
      }),
    );

    // Default mock implementations
    mockListAgentProjects.mockResolvedValue({
      status: 'success',
      projects: [mockProject],
    });
    mockGetAgentProject.mockResolvedValue({
      status: 'success',
      project: mockProject,
    });
    // Initial workspace is empty (no active run)
    mockGetAgentWorkspace.mockResolvedValue(mockEmptyWorkspaceResponse);
    mockListAgentProjectTasks.mockResolvedValue({
      status: 'success',
      projectId: TEST_PROJECT_ID,
      tasks: [],
      limit: 20,
    });
    mockGetAgentRunArtifacts.mockResolvedValue({ status: 'success', artifacts: null });
    mockGetAgentRunTimeline.mockResolvedValue({ status: 'success', timeline: [] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('handleCreateTask', () => {
    it('calls createAgentRun with current projectId when creating a task', async () => {
      mockCreateAgentRun.mockResolvedValue(mockRunResponse);
      // After creation, workspace returns the new run
      mockGetAgentWorkspace.mockResolvedValue(mockEmptyWorkspaceResponse);

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      // Wait for initial load
      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      // Find the prompt input and type a research question
      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
      const promptInput = screen.getByLabelText('创建研究任务');
      fireEvent.change(promptInput, { target: { value: 'Test research question' } });

      // Find and click the send/create button
      const sendButton = screen.getByTitle('启动 Agent 任务');
      fireEvent.click(sendButton);

      // Wait for the API call
      await waitFor(() => {
        expect(mockCreateAgentRun).toHaveBeenCalled();
      });

      // Verify createAgentRun was called with correct projectId
      expect(mockCreateAgentRun).toHaveBeenCalledWith(
        TEST_PROJECT_ID,
        expect.objectContaining({
          prompt: 'Test research question',
        }),
      );
    });

    it('does NOT call runAgentGraph or createAgentTask when creating a task', async () => {
      mockCreateAgentRun.mockResolvedValue(mockRunResponse);
      mockGetAgentWorkspace.mockResolvedValue(mockEmptyWorkspaceResponse);

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
      const promptInput = screen.getByLabelText('创建研究任务');
      fireEvent.change(promptInput, { target: { value: 'Test research question' } });

      const sendButton = screen.getByTitle('启动 Agent 任务');
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(mockCreateAgentRun).toHaveBeenCalled();
      });

      // Verify legacy APIs were NOT called
      expect(mockRunAgentGraph).not.toHaveBeenCalled();
      expect(mockCreateAgentTask).not.toHaveBeenCalled();
    });

    it('displays the returned run before workspace refresh completes', async () => {
      mockCreateAgentRun.mockResolvedValue(mockRunResponse);
      mockGetAgentWorkspace.mockResolvedValue(mockEmptyWorkspaceResponse);
      await act(async () => {
        render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);
      });
      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
      let resolveRefresh!: (value: typeof mockWorkspaceResponse) => void;
      mockGetAgentWorkspace.mockImplementation(() => new Promise((resolve) => { resolveRefresh = resolve; }));
      fireEvent.change(screen.getByLabelText('创建研究任务'), { target: { value: 'Test research question' } });
      fireEvent.click(screen.getByTitle('启动 Agent 任务'));
      await waitFor(() => expect(mockCreateAgentRun).toHaveBeenCalled());
      await screen.findByText('等待计划确认');
      expect(mockCreateAgentRun).toHaveBeenCalledWith(TEST_PROJECT_ID, expect.objectContaining({ prompt: 'Test research question' }));
      const snapshot = JSON.parse(localStorageMock.getItem('pixiu-agent-workspace')!);
      expect(snapshot.currentTask).toMatchObject({ taskId: TEST_RUN_ID, projectId: TEST_PROJECT_ID, prompt: 'Test research question' });
      expect(snapshot.tasksByProjectId[TEST_PROJECT_ID]).toEqual(expect.arrayContaining([
        expect.objectContaining({ taskId: TEST_RUN_ID, projectId: TEST_PROJECT_ID }),
      ]));
      await act(async () => { resolveRefresh(mockWorkspaceResponse); });
    });
    it('keeps task and shows error when workspace refresh fails after creation', async () => {
      mockCreateAgentRun.mockResolvedValue(mockRunResponse);

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      // Wait for initial load to complete
      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      // Wait a bit for all initialization to complete
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
      });

      // Now set up the mock to fail for the next call (after creation)
      mockGetAgentWorkspace.mockRejectedValueOnce(new Error('Network error'));

      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
      const promptInput = screen.getByLabelText('创建研究任务');
      fireEvent.change(promptInput, { target: { value: 'Test research question' } });

      const sendButton = screen.getByTitle('启动 Agent 任务');
      fireEvent.click(sendButton);

      // Wait for task to appear (cached immediately after creation)
      await waitFor(() => {
        expect(screen.getByText('等待计划确认')).toBeInTheDocument();
      });

      // Verify error message is displayed
      await waitFor(() => {
        expect(screen.getByText(/任务已创建，但工作区刷新失败/i)).toBeInTheDocument();
      });

      // Verify input was cleared
      expect((screen.getByLabelText('创建研究任务') as HTMLTextAreaElement).value).toBe('');

      // Verify createAgentRun was called only once
      expect(mockCreateAgentRun).toHaveBeenCalledTimes(1);
    });

    it('shows contract error when createAgentRun returns empty runId', async () => {
      mockCreateAgentRun.mockResolvedValue({
        status: 'success',
        run: { runId: '', projectId: TEST_PROJECT_ID },
      });

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
      const promptInput = screen.getByLabelText('创建研究任务');
      fireEvent.change(promptInput, { target: { value: 'Test research question' } });

      const sendButton = screen.getByTitle('启动 Agent 任务');
      fireEvent.click(sendButton);

      // Wait for error to appear
      await waitFor(() => {
        expect(screen.getByText(/后端未返回 runId/i)).toBeInTheDocument();
      });

      // Verify task was NOT cached (no task status badge in UI)
      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
    });

    it('shows contract error when createAgentRun returns empty projectId', async () => {
      mockCreateAgentRun.mockResolvedValue({
        status: 'success',
        run: { runId: TEST_RUN_ID, projectId: '' },
      });

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
      const promptInput = screen.getByLabelText('创建研究任务');
      fireEvent.change(promptInput, { target: { value: 'Test research question' } });

      const sendButton = screen.getByTitle('启动 Agent 任务');
      fireEvent.click(sendButton);

      // Wait for error to appear
      await waitFor(() => {
        expect(screen.getByText(/后端未返回 projectId/i)).toBeInTheDocument();
      });

      // Verify task was NOT cached
      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
    });

    it('shows contract error when createAgentRun returns wrong projectId', async () => {
      const wrongProjectId = 'wrong-project-789';
      mockCreateAgentRun.mockResolvedValue({
        status: 'success',
        run: { runId: TEST_RUN_ID, projectId: wrongProjectId },
      });

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
      const promptInput = screen.getByLabelText('创建研究任务');
      fireEvent.change(promptInput, { target: { value: 'Test research question' } });

      const sendButton = screen.getByTitle('启动 Agent 任务');
      fireEvent.click(sendButton);

      // Wait for error to appear
      await waitFor(() => {
        expect(screen.getByText(/与当前项目.*不一致/i)).toBeInTheDocument();
      });

      // Verify task was NOT cached
      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
    });

    it('displays error message when createAgentRun fails', async () => {
      const errorMessage = 'Backend error: Project not found';
      mockCreateAgentRun.mockRejectedValue({
        response: { data: { message: errorMessage } },
      });

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      expect(screen.queryByText('等待计划确认')).not.toBeInTheDocument();
      const promptInput = screen.getByLabelText('创建研究任务');
      fireEvent.change(promptInput, { target: { value: 'Test research question' } });

      const sendButton = screen.getByTitle('启动 Agent 任务');
      fireEvent.click(sendButton);

      // Wait for error to appear in UI
      await waitFor(() => {
        expect(screen.getByText(new RegExp(errorMessage, 'i'))).toBeInTheDocument();
      });
    });
  });

  describe('polling', () => {
    it('does NOT call getAgentGraphState during polling', async () => {
      // Set up a task in progress
      const runningTask = {
        ...mockRunResponse.run,
        status: 'running',
      };
      localStorageMock.setItem(
        'pixiu-agent-workspace',
        JSON.stringify({
          projects: [mockProject],
          activeProjectId: TEST_PROJECT_ID,
          activeProject: mockProject,
          activeWorkspace: null,
          latestTask: runningTask,
          currentTask: { ...runningTask, taskId: TEST_RUN_ID },
          tasksByProjectId: { [TEST_PROJECT_ID]: [{ ...runningTask, taskId: TEST_RUN_ID }] },
          nextProjectNumber: 2,
        }),
      );

      mockGetAgentWorkspace.mockResolvedValue({
        ...mockWorkspaceResponse,
        workspace: {
          ...mockWorkspaceResponse.workspace,
          activeRun: runningTask,
        },
      });

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      // Clear initialization calls
      mockGetAgentWorkspace.mockClear();

      // Wait for polling to trigger (> 800ms)
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 1000));
      });

      // Verify getAgentGraphState was NOT called
      expect(mockGetAgentGraphState).not.toHaveBeenCalled();
      // Verify workspace polling was called
      expect(mockGetAgentWorkspace).toHaveBeenCalled();
    });

    it('uses getAgentWorkspace for polling after initialization', async () => {
      const runningTask = {
        ...mockRunResponse.run,
        status: 'running',
      };
      localStorageMock.setItem(
        'pixiu-agent-workspace',
        JSON.stringify({
          projects: [mockProject],
          activeProjectId: TEST_PROJECT_ID,
          activeProject: mockProject,
          activeWorkspace: null,
          latestTask: runningTask,
          currentTask: { ...runningTask, taskId: TEST_RUN_ID },
          tasksByProjectId: { [TEST_PROJECT_ID]: [{ ...runningTask, taskId: TEST_RUN_ID }] },
          nextProjectNumber: 2,
        }),
      );

      mockGetAgentWorkspace.mockResolvedValue({
        ...mockWorkspaceResponse,
        workspace: {
          ...mockWorkspaceResponse.workspace,
          activeRun: runningTask,
        },
      });

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      await waitFor(() => {
        expect(mockGetAgentWorkspace).toHaveBeenCalledWith(TEST_PROJECT_ID);
      });

      // Clear initialization calls
      mockGetAgentWorkspace.mockClear();

      // Wait for polling to trigger (> 800ms)
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 1000));
      });

      // Verify polling called workspace
      expect(mockGetAgentWorkspace).toHaveBeenCalledWith(TEST_PROJECT_ID);
    });

    it('preserves evidenceItems and draftReport when workspace fails but getAgentRun succeeds', async () => {
      // Set up a task with existing artifacts
      const taskWithArtifacts = {
        ...mockRunResponse.run,
        status: 'running',
        taskId: TEST_RUN_ID,
        runId: TEST_RUN_ID,
        evidenceItems: [{ sourceId: 'ev-1', text: 'Existing evidence', pageIndex: 0, pdfId: 'paper-1' }],
        draftReport: 'Existing draft report content',
        findings: [{ findingId: 'f-1', summary: 'Existing finding', sourceIds: ['ev-1'] }],
        events: [{ eventId: 'e-1', type: 'progress', timestamp: '2026-01-01', stage: 'researching', summary: 'Existing event' }],
      };
      localStorageMock.setItem(
        'pixiu-agent-workspace',
        JSON.stringify({
          projects: [mockProject],
          activeProjectId: TEST_PROJECT_ID,
          activeProject: mockProject,
          activeWorkspace: null,
          latestTask: taskWithArtifacts,
          currentTask: taskWithArtifacts,
          tasksByProjectId: { [TEST_PROJECT_ID]: [taskWithArtifacts] },
          nextProjectNumber: 2,
        }),
      );

      mockGetAgentWorkspace.mockResolvedValue({
        ...mockWorkspaceResponse,
        workspace: {
          ...mockWorkspaceResponse.workspace,
          activeRun: taskWithArtifacts,
          latestArtifacts: {
            evidenceItems: taskWithArtifacts.evidenceItems,
            draftReport: taskWithArtifacts.draftReport,
            findings: taskWithArtifacts.findings,
          },
          timeline: [{ id: 'e-1', type: 'progress', timestamp: '2026-01-01', phase: 'researching', detail: 'Existing event' }],
        },
      });
      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      // Wait for initial load to complete
      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      // Wait a bit for initialization to complete
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
      });

      // Now make workspace fail for polling
      mockGetAgentWorkspace.mockRejectedValue(new Error('Workspace unavailable'));
      mockGetAgentRun.mockResolvedValue({
        status: 'success',
        run: { ...mockRunResponse.run, status: 'running' },
      });
      // Artifacts and timeline also fail (simulating network issues)
      mockGetAgentRunArtifacts.mockRejectedValue(new Error('Artifacts unavailable'));
      mockGetAgentRunTimeline.mockRejectedValue(new Error('Timeline unavailable'));

      // Wait for polling to trigger and fallback to execute
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 1200));
      });

      // Verify fallback APIs were called
      expect(mockGetAgentRun).toHaveBeenCalled();

      await waitFor(() => {
        const snapshot = JSON.parse(localStorageMock.getItem('pixiu-agent-workspace')!);
        expect(snapshot.currentTask).toMatchObject({
          taskId: TEST_RUN_ID,
          evidenceItems: [expect.objectContaining({ sourceId: 'ev-1', text: 'Existing evidence' })],
          draftReport: 'Existing draft report content',
          findings: [expect.objectContaining({ summary: 'Existing finding' })],
          events: [expect.objectContaining({ eventId: 'e-1', summary: 'Existing event', stage: 'researching' })],
        });
      });
    });
  });

  describe('handleReviewPlan', () => {
    it('calls reviewAgentRunPlan when clicking confirm plan button', async () => {
      const awaitingTask = {
        ...mockRunResponse.run,
        status: 'awaiting_plan_review',
        taskId: TEST_RUN_ID,
        runId: TEST_RUN_ID,
        planItems: [{ id: 'retrieve', label: 'Retrieve papers' }],
      };
      localStorageMock.setItem(
        'pixiu-agent-workspace',
        JSON.stringify({
          projects: [mockProject],
          activeProjectId: TEST_PROJECT_ID,
          activeProject: mockProject,
          activeWorkspace: mockWorkspaceResponse.workspace,
          latestTask: awaitingTask,
          currentTask: awaitingTask,
          tasksByProjectId: { [TEST_PROJECT_ID]: [awaitingTask] },
          nextProjectNumber: 2,
        }),
      );

      mockGetAgentWorkspace.mockResolvedValue({
        ...mockWorkspaceResponse,
        workspace: {
          ...mockWorkspaceResponse.workspace,
          activeRun: awaitingTask,
        },
      });
      mockReviewAgentRunPlan.mockResolvedValue({ status: 'success', run: awaitingTask });

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      // Find and click the "确认计划并执行" button
      const confirmButton = await screen.findByText('确认计划并执行');
      fireEvent.click(confirmButton);

      // Wait for API call
      await waitFor(() => {
        expect(mockReviewAgentRunPlan).toHaveBeenCalled();
      });

      // Verify reviewAgentRunPlan was called with correct runId
      expect(mockReviewAgentRunPlan).toHaveBeenCalledWith(
        TEST_RUN_ID,
        expect.anything(),
      );

      // Verify legacy APIs were NOT called
      expect(mockResumeAgentGraph).not.toHaveBeenCalled();
      expect(mockReviewAgentPlan).not.toHaveBeenCalled();
    });
  });

  describe('handleReviewFinal', () => {
    it('calls reviewAgentRunFinal when task is awaiting final review', async () => {
      const awaitingFinalTask = {
        ...mockRunResponse.run,
        status: 'awaiting_final_review',
        taskId: TEST_RUN_ID,
        runId: TEST_RUN_ID,
        draftReport: 'Final draft report',
      };
      localStorageMock.setItem(
        'pixiu-agent-workspace',
        JSON.stringify({
          projects: [mockProject],
          activeProjectId: TEST_PROJECT_ID,
          activeProject: mockProject,
          activeWorkspace: {
            ...mockWorkspaceResponse.workspace,
            activeRun: awaitingFinalTask,
          },
          latestTask: awaitingFinalTask,
          currentTask: awaitingFinalTask,
          tasksByProjectId: { [TEST_PROJECT_ID]: [awaitingFinalTask] },
          nextProjectNumber: 2,
        }),
      );

      mockGetAgentWorkspace.mockResolvedValue({
        ...mockWorkspaceResponse,
        workspace: {
          ...mockWorkspaceResponse.workspace,
          activeRun: awaitingFinalTask,
        },
      });
      mockReviewAgentRunFinal.mockResolvedValue({ status: 'success', run: awaitingFinalTask });

      render(<AgentWorkspace paperLibrary={[{ id: 'paper-1' }]} activePaperId="paper-1" />);

      await waitFor(() => {
        expect(mockListAgentProjects).toHaveBeenCalled();
      });

      const confirmButton = await screen.findByRole('button', { name: '确认终稿' });
      fireEvent.change(screen.getByPlaceholderText('终稿审查备注（可选）'), {
        target: { value: '已核对原文' },
      });
      fireEvent.click(confirmButton);
      await waitFor(() => {
        expect(mockReviewAgentRunFinal).toHaveBeenCalledWith(TEST_RUN_ID, {
          reviewNotes: '已核对原文', riskReviews: [],
        });
      });
      expect(mockResumeAgentGraph).not.toHaveBeenCalled();
      expect(mockReviewAgentFinal).not.toHaveBeenCalled();
    });
  });
});
