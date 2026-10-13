import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({ task: null, chatProps: null, failAnswerSave: false, writes: 0, startOperation: vi.fn(), researchGet: vi.fn(), researchAction: vi.fn(), retainDraft: vi.fn(async () => {}), api: { sendTaskMessage: vi.fn(), criticalReading: vi.fn(), backgroundKnowledge: vi.fn() } }));
const materialProcessing = vi.hoisted(() => vi.fn(async () => undefined));
const operationList = vi.hoisted(() => vi.fn(async () => []));
const recoverOperation = vi.hoisted(() => vi.fn());
const localDbGet = vi.hoisted(() => vi.fn(async () => null));
const localDbPut = vi.hoisted(() => vi.fn(async () => {}));
vi.mock('./hooks/useTaskWorkspace', () => ({ useTaskWorkspace: () => ({
  tasks: [state.task, ...(state.otherTasks || [])], activeTask: state.task, activeTaskId: state.task.id,
  adoptServerTask: async task => { if (state.failAnswerSave) throw new Error('本地缓存未更新'); state.task = task; },
  updateTask: async (id, updater) => {
    if (id !== state.task.id) throw new Error('wrong task');
    if (state.beforeUpdate) { const mutate = state.beforeUpdate; state.beforeUpdate = null; mutate(); }
    const patch = typeof updater === 'function' ? updater(state.task) : updater;
    state.writes += 1;
    if (state.failAnswerSave && patch.messages?.at(-1)?.role === 'ai') {
      throw Object.assign(new Error('本地草稿已保留'), { code: 'TASK_CONFLICT' });
    }
    state.task = { ...state.task, ...patch };
    return state.task;
  }, selectTask: id => { state.selectedTaskId = id; }, createTask: vi.fn(),
}) }));
vi.mock('./services/api', () => ({ apiService: state.api }));
vi.mock('./services/taskWorkspaceApi', () => ({ taskWorkspaceApi: {
  startOperation: state.startOperation, listOperations: operationList, recoverOperationResult: recoverOperation, listMaterials: async () => [],
  getMaterialProcessing: materialProcessing,
  getMaterialFile: async () => { throw new Error('旧论文尚未保存到服务端'); },
  getMaterialAnalysis: async () => { throw new Error('旧论文尚未保存到服务端'); },
} }));
vi.mock('./services/taskResearchApi', () => ({ taskResearchApi: { get: state.researchGet, action: state.researchAction, capabilities: vi.fn(async () => null), addSource: vi.fn(async () => ({})) } }));
vi.mock('./services/taskWorkspaceRemoteStore', () => ({ taskWorkspaceRemoteStore: { getUnsyncedDraft: async () => null, retainUnsyncedDraft: state.retainDraft } }));
vi.mock('./services/localDb', () => ({ initDB: async () => ({
  getAll: async () => [{ id: 'a', title: '论文甲' }, { id: 'b', title: '论文乙' }],
  get: localDbGet, put: localDbPut,
}) }));
vi.mock('./hooks/useThemePreference', () => ({ useThemePreference: () => ({ theme: 'light', toggleTheme: vi.fn() }) }));
vi.mock('./hooks/useCompactLayout', () => ({ default: () => Boolean(state.compact) }));
vi.mock('./hooks/useWorkbenchWidth', () => ({ default: () => state.width || 1440 }));
vi.mock('./hooks/usePageTranslation', async () => {
  const actual = await vi.importActual('./hooks/usePageTranslation');
  return { usePageTranslation: props => {
  state.translationProps = props;
  if (state.realTranslation) return actual.usePageTranslation({ ...props, apiService: { translatePage: state.translatePage } });
  return {handlePdfPageChange: props.setPdfPageState};
} }; });
vi.mock('./components/PdfViewer', () => ({ default: function MockPdfViewer(props) {
  state.pdfProps = props;
  const initial = React.useRef(props);
  React.useEffect(() => {
    state.pdfMounts = (state.pdfMounts || 0) + 1;
    initial.current.onPageChange({pageIndex: initial.current.targetPageIndex || 0, totalPages: 19});
    return () => { state.pdfUnmounts = (state.pdfUnmounts || 0) + 1; };
  }, []);
  return <div data-testid="paper-viewer" />;
} }));
vi.mock('./components/TranslationPanel', () => ({ default: props => { state.translationPanelProps = props; return null; } }));
vi.mock('./components/ChatPanel', () => ({ default: (props) => { state.chatProps = props; return <div data-testid="chat">
  {props.currentActivity}{props.composerContext}{props.messages?.map((message, index) => <React.Fragment key={message.id || index}>{props.renderMessageAfter?.(message, index)}</React.Fragment>)}{props.historyContent}
</div>; } }));
import UnifiedTaskApp from './UnifiedTaskApp';

describe('unified task conversation wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localDbGet.mockImplementation(async () => null);
    localDbPut.mockImplementation(async () => {});
    operationList.mockResolvedValue([]);
    state.researchGet.mockRejectedValue(new Error('测试研究不存在'));
    state.researchAction.mockRejectedValue(new Error('测试未配置研究操作'));
    materialProcessing.mockImplementation(async () => undefined);
    localStorage.clear();
    state.failAnswerSave = false;
    state.compact = false;
    state.width = 1440;
    state.realTranslation = false;
    state.writes = 0;
    state.beforeUpdate = null;
    state.otherTasks = [];
    state.selectedTaskId = null;
    state.pdfMounts = 0;
    state.pdfUnmounts = 0;
    state.task = { id: 'task', title: '任务', paperIds: ['a', 'b'], focusedPaperId: null,
      messages: [], notes: [], artifacts: [], activeActivity: { id: 'lesson', paperIds: ['a'], primaryPaperId: 'a' } };
    state.startOperation.mockImplementation(async (taskId, request) => {
      const context = { taskId, ...request.input };
      const task = { ...state.task, messages: [...state.task.messages,
        { role: 'user', content: request.input.displayText },
        { role: 'ai', content: '回答', context, sentenceSourceMap: [{ target: 'message', sentence: '回答', sourceIds: ['s'] }] }],
        artifacts: request.input.capability === 'chat' ? state.task.artifacts : [...state.task.artifacts, { id: request.requestId + ':artifact', text: '完整成果', paperIds: request.input.allowedPaperIds }],
      };
      return { taskId, ...request, status: 'succeeded', task };
    });
  });

  it('asks once for an ambiguous critique object and retains the question until selection', async () => {
    state.task.activeActivity = null;
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onSendMessage('/批判 画质几乎不变可信吗'));
    expect(state.startOperation).not.toHaveBeenCalled();
    expect(screen.getByRole('group', { name: '选择批判对象' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '分别分析全部' }));
    await waitFor(() => expect(state.startOperation).toHaveBeenCalled());
    expect(state.startOperation.mock.calls[0][1].input).toMatchObject({
      message: '画质几乎不变可信吗', allowedPaperIds: ['a', 'b'], targetPaperIds: ['a', 'b'], capability: 'critique',
    });
  });

  it('uses the currently open paper as critique target while permitting all task materials', async () => {
    state.task.activeActivity = null;
    state.task.focusedPaperId = 'b';
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onSendMessage('/批判 画质几乎不变可信吗，只给两点'));
    expect(state.startOperation.mock.calls[0][1].input).toMatchObject({
      allowedPaperIds: ['a', 'b'], targetPaperIds: ['b'], message: '画质几乎不变可信吗，只给两点',
    });
  });

  it('resizes with keyboard boundaries and restores hidden desktop panes', () => {
    render(<UnifiedTaskApp />);
    const resize = screen.getByRole('separator', { name: '调整阅读与对话宽度' });
    fireEvent.keyDown(resize, { key: 'ArrowRight' });
    expect(resize).toHaveAttribute('aria-valuenow', '68');
    fireEvent.keyDown(resize, { key: 'End' });
    fireEvent.keyDown(resize, { key: 'ArrowRight' });
    expect(resize.getAttribute('aria-valuenow')).toBe(resize.getAttribute('aria-valuemax'));
    fireEvent.keyDown(resize, { key: 'Home' });
    expect(resize.getAttribute('aria-valuenow')).toBe(resize.getAttribute('aria-valuemin'));
    fireEvent.click(screen.getByRole('button', { name: '收起阅读区' }));
    expect(screen.getByRole('region', { name: '论文与成果' })).toHaveClass('unified-desktop-hidden');
    fireEvent.click(screen.getByRole('button', { name: '展开阅读区' }));
    expect(screen.getByRole('region', { name: '论文与成果' })).not.toHaveClass('unified-desktop-hidden');
  });

  it('keeps layout selection consistent with collapse and preserves resized proportions', () => {
    render(<UnifiedTaskApp />);
    fireEvent.keyDown(screen.getByRole('separator', { name: '调整阅读与对话宽度' }), { key: 'ArrowRight' });
    fireEvent.click(screen.getByRole('button', { name: '收起阅读区' }));
    fireEvent.click(screen.getByRole('button', { name: '布局', exact: true }));
    expect(screen.getByRole('button', { name: '仅对话', exact: true })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('button', { name: '重置栏宽' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '阅读与对话', exact: true }));
    expect(screen.getByRole('separator', { name: '调整阅读与对话宽度' })).toHaveAttribute('aria-valuenow', '68');
    expect(screen.getByRole('region', { name: '论文与成果' })).not.toHaveClass('unified-desktop-hidden');
  });

  it('offers only usable single-pane layouts on compact screens', () => {
    state.compact = true;
    render(<UnifiedTaskApp />);
    fireEvent.click(screen.getByRole('button', { name: '布局', exact: true }));
    expect(screen.queryByRole('button', { name: '阅读与对话', exact: true })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '仅阅读', exact: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '仅对话', exact: true })).toBeInTheDocument();
  });

  it('clears contextual return when opening the original normally', async () => {
    state.task.focusedPaperId = 'a';
    state.task.notes = [{ id: 'n', title: '实验笔记', text: '正文' }];
    render(<UnifiedTaskApp />);
    expect(screen.queryByRole('button', { name: '返回记录' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '实验笔记 · 笔记' }));
    await act(async () => state.chatProps.onJumpToSource({ pdfId: 'a', pageIndex: 3 }));
    fireEvent.click(screen.getByRole('button', { name: '返回笔记' }));
    fireEvent.click(screen.getByRole('button', { name: '查看原文', exact: true }));
    expect(screen.queryByRole('button', { name: '返回笔记' })).not.toBeInTheDocument();
  });

  it('waits for a slow translation cache read before persisting any replacement', async () => {
    state.task.focusedPaperId = 'a';
    localStorage.setItem('pixiu-reading-position:["task","a"]','6');
    let finish;
    localDbGet.mockImplementation(store => store === 'translationStore'
      ? new Promise(resolve => { finish = resolve; }) : Promise.resolve(null));
    render(<UnifiedTaskApp />);
    await waitFor(() => expect(finish).toBeTypeOf('function'));
    await act(async () => { await new Promise(resolve => setTimeout(resolve,400)); });
    expect(localDbPut.mock.calls.filter(call => call[0] === 'translationStore')).toHaveLength(0);
    expect(state.translationProps.translationState.currentPage).toBe(6);
    act(() => {
      state.translationProps.setPdfPageState({pageIndex:8,totalPages:19});
      state.translationProps.commitTranslationState(current => ({...current,currentPage:8}));
    });
    await act(async () => finish({pdfId:'a',currentPage:3,pages:{3:{status:'success',translatedText:'已有第四页译文'}}}));
    await waitFor(() => expect(localDbPut).toHaveBeenCalledWith('translationStore',
      expect.objectContaining({currentPage:8,pages:expect.objectContaining({3:expect.objectContaining({translatedText:'已有第四页译文'})})}), 'a'));
    expect(state.translationProps.pdfPageState.pageIndex).toBe(8);
  });

  it('keeps invalid learning input and shows its actionable error above service query errors', async () => {
    state.task.paperIds = [];
    state.task.activeActivity = null;
    operationList.mockRejectedValue(new Error('服务状态不可读取'));
    render(<UnifiedTaskApp />);
    await screen.findByText('暂时无法确认结果');
    let accepted;
    await act(async () => { accepted = await state.chatProps.onSendMessage('/精读 帮我读这篇论文'); });
    expect(accepted).toBe(false);
    expect(screen.getByRole('alert')).toHaveTextContent('请打开或明确指定一篇要学习的论文');
    expect(state.startOperation).not.toHaveBeenCalled();
    expect(state.chatProps.conversationId).toBe('task');
    expect(state.chatProps.starterPrompts).toHaveLength(1);
  });

  it('keeps the task unchanged after an upload fails and shows a plain recovery message', async () => {
    const upload = vi.fn().mockRejectedValue(new Error('Request failed with status code 500'));
    state.api.uploadTaskMaterial = upload;
    const initial = { ...state.task };
    const view = render(<UnifiedTaskApp />);
    fireEvent.change(view.container.querySelector('input[type="file"]'), { target: { files: [new File(['%PDF-'], '论文.pdf', { type: 'application/pdf' })] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('论文上传未完成，请重新选择文件再试');
    expect(state.task).toEqual(initial);
    expect(state.selectedTaskId).toBeNull();
    expect(state.writes).toBe(0);
    expect(upload).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: '添加论文' }));
    expect(screen.getByRole('button', { name: '上传 PDF' })).toBeEnabled();
  });

  it('rejects unsupported files before creating or uploading anything', async () => {
    state.api.uploadTaskMaterial = vi.fn();
    const view = render(<UnifiedTaskApp />);
    fireEvent.change(view.container.querySelector('input[type="file"]'), { target: { files: [new File(['text'], '说明.txt')] } });
    expect(screen.getByRole('alert')).toHaveTextContent('请选择 PDF 论文文件');
    expect(state.api.uploadTaskMaterial).not.toHaveBeenCalled();
    expect(state.writes).toBe(0);
  });
  it('cancels a pending upload and ignores late completion without attaching the material', async () => {
    let finish;
    state.api.uploadTaskMaterial = vi.fn(() => new Promise(resolve => { finish = resolve; }));
    const view = render(<UnifiedTaskApp />);
    fireEvent.change(view.container.querySelector('input[type="file"]'), { target: { files: [new File(['%PDF-'], '待上传.pdf', { type: 'application/pdf' })] } });
    await waitFor(() => expect(state.api.uploadTaskMaterial).toHaveBeenCalledOnce());
    const signal = state.api.uploadTaskMaterial.mock.calls[0][1];
    fireEvent.click(screen.getByRole('button', { name: '取消上传' }));
    expect(signal.aborted).toBe(true);
    await act(async () => finish({ status: 'success', pdfId: 'late' }));
    expect(state.task.paperIds).toEqual(['a', 'b']);
    expect(state.writes).toBe(0);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('opens a new blank note directly in edit mode and creates it once', async () => {
    render(<UnifiedTaskApp />);
    fireEvent.click(screen.getByRole('button', { name: '新建笔记' }));
    expect(await screen.findByRole('textbox', { name: '编辑笔记与成果' })).toHaveValue('');
    expect(state.task.notes).toHaveLength(1);
    expect(screen.getByRole('button', { name: '完成编辑' })).toBeInTheDocument();
  });

  it('rejects insufficient comparison materials without adding a fake answer to the conversation', async () => {
    state.task.paperIds = ['a'];
    state.task.activeActivity = null;
    render(<UnifiedTaskApp />);
    let accepted;
    await act(async () => { accepted = await state.chatProps.onSendMessage('/比较 这两篇论文'); });
    expect(accepted).toBe(false);
    expect(screen.getByRole('alert')).toHaveTextContent('比较至少需要两篇论文');
    expect(state.task.messages).toEqual([]);
    expect(state.startOperation).not.toHaveBeenCalled();
  });

  it('keeps desktop preferences and note drafts while compact panes and navigation change', () => {
    state.compact = true;
    state.task.notes = [{ id: 'compact-note', title: '窄屏笔记', text: '已保存' }];
    render(<UnifiedTaskApp />);
    const savedLayout = localStorage.getItem('pixiu-unified-layout-v1');
    fireEvent.click(screen.getByRole('button', { name: '任务与材料' }));
    expect(screen.getByRole('region', { name: '任务对话' })).toHaveAttribute('inert');
    expect(screen.getByRole('button', { name: '收起导航' })).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: '窄屏笔记 · 笔记' }));
    expect(screen.getByRole('button', { name: '任务与材料' })).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(screen.getByRole('button', { name: '编辑', exact: true }));
    fireEvent.change(screen.getByRole('textbox', { name: '编辑笔记与成果' }), { target: { value: '窄屏草稿' } });
    fireEvent.click(screen.getByRole('group', { name: '内容视图' }).querySelector('button:last-child'));
    fireEvent.click(screen.getByRole('group', { name: '内容视图' }).querySelector('button:nth-child(2)'));
    expect(screen.getByRole('textbox', { name: '编辑笔记与成果' })).toHaveValue('窄屏草稿');
    expect(localStorage.getItem('pixiu-unified-layout-v1')).toBe(savedLayout);
    expect(localStorage.getItem('pixiu-compact-pane-v1')).toBe('reader');
    fireEvent.click(screen.getByRole('button', { name: '任务与材料' }));
    fireEvent.keyDown(screen.getByRole('button', { name: '收起导航' }), { key: 'Escape' });
    expect(screen.getByRole('button', { name: '任务与材料' })).toHaveFocus();
    expect(screen.getByRole('region', { name: '论文与成果' })).not.toHaveAttribute('inert');
  });

  it('adapts a medium window temporarily and restores saved widths on widening', () => {
    const { rerender } = render(<UnifiedTaskApp />);
    fireEvent.keyDown(screen.getByRole('separator', { name: '调整导航宽度' }), { key: 'ArrowRight' });
    const preference = localStorage.getItem('pixiu-unified-layout-v1');
    expect(JSON.parse(preference).navWidth).toBe(240);
    state.width = 1280;
    rerender(<UnifiedTaskApp />);
    expect(screen.queryByRole('separator', { name: '调整导航宽度' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '展开导航' }));
    expect(screen.getByRole('dialog', { name: '任务与材料' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '任务对话' })).toHaveAttribute('inert');
    fireEvent.keyDown(screen.getByRole('button', { name: '收起导航' }), { key: 'Escape' });
    expect(screen.getByRole('button', { name: '展开导航' })).toHaveFocus();
    state.width = 1440;
    rerender(<UnifiedTaskApp />);
    expect(screen.getByRole('separator', { name: '调整导航宽度' })).toHaveAttribute('aria-valuenow', '240');
    expect(localStorage.getItem('pixiu-unified-layout-v1')).toBe(preference);
  });

  it('stops polling missing legacy material records without starting any generation', async () => {
    vi.useFakeTimers();
    try {
      materialProcessing.mockRejectedValue({ response: { status: 404 } });
      render(<UnifiedTaskApp />);
      await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
      expect(materialProcessing).toHaveBeenCalledTimes(2);
      expect(state.startOperation).not.toHaveBeenCalled();
      expect(screen.getByTestId('chat')).toBeDefined();
    } finally { vi.useRealTimers(); }
  });

  it('routes a natural comparison over the task without overwriting a paused lesson', async () => {
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onSendMessage('请帮我比较两篇论文的方法'));
    expect(state.startOperation).toHaveBeenCalledWith('task', expect.objectContaining({ kind: 'conversation.execute', input: expect.objectContaining({ capability: 'compare', allowedPaperIds: ['a', 'b'], primaryPaperId: null }) }));
    expect(state.api.sendTaskMessage).not.toHaveBeenCalled();
    expect(state.task.activeActivity.id).toBe('lesson');
    expect(state.task.artifacts[0].paperIds).toEqual(['a', 'b']);
  });

  it('opens a moved artifact in the new task and keeps its unsaved local draft without generating again', async () => {
    const original = state.task;
    const target = { ...original, id: 'target', title: '目标任务', messages: [],
      artifacts: [{ id: 'moved-result', title: '已移动成果', text: '已保存正文', paperIds: ['a'] }] };
    state.otherTasks = [target];
    const draftKey = 'pixiu-document-draft:' + JSON.stringify(['target', 'artifacts', 'moved-result']);
    localStorage.setItem(draftKey, '目标任务未保存草稿');
    localStorage.setItem(draftKey + ':base', JSON.stringify('已保存正文'));
    const view = render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onOpenArtifact('moved-result'));
    expect(state.selectedTaskId).toBe('target');
    state.task = target;
    state.otherTasks = [original];
    view.rerender(<UnifiedTaskApp />);
    expect(await screen.findByRole('article', { name: '成果正文' })).toHaveTextContent('目标任务未保存草稿');
    expect(screen.getByText('未保存修改')).toBeInTheDocument();
    expect(target.artifacts[0].text).toBe('已保存正文');
    expect(state.startOperation).not.toHaveBeenCalled();
    expect(state.writes).toBe(0);
  });

  it('opens a conflicted full result in the middle pane and saves it without rerunning or replacing a lesson', async () => {
    const record = { taskId: 'task', requestId: 'conflict', kind: 'learning.start', status: 'conflicted',
      paperIds: ['a'], request: { goal: '原学习目标' }, result: { message: '短结果', sources: [],
        materialScope: { taskId: 'task', allowedPaperIds: ['a'] },
        artifact: { text: '完整解释和证据', paperIds: ['a'], sources: [] } } };
    operationList.mockResolvedValue([record]);
    recoverOperation.mockImplementation(async () => ({ ...record, status: 'succeeded', task: { ...state.task,
      artifacts: [{ id: 'conflict:artifact', sourceRequestId: 'conflict', text: '完整解释和证据', paperIds: ['a'] }] } }));
    render(<UnifiedTaskApp />);
    fireEvent.click(await screen.findByRole('button', { name: '打开已生成结果' }));
    expect(screen.getByRole('region', { name: '论文与成果' })).toHaveTextContent('完整解释和证据');
    expect(screen.getByRole('region', { name: '任务对话' })).not.toHaveTextContent('完整解释和证据');
    fireEvent.click(screen.getByRole('button', { name: '保存为成果' }));
    await waitFor(() => expect(screen.getByRole('article', { name: '成果正文' })).toHaveTextContent('完整解释和证据'));
    expect(recoverOperation).toHaveBeenCalledWith('task', 'conflict');
    expect(state.startOperation).not.toHaveBeenCalled();
    expect(state.task.activeActivity.id).toBe('lesson');
  });

  it('routes explicit combined actions through the bounded adapter with the full task scope', async () => {
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onSendMessage('请先补齐前置知识，再比较两篇论文的方法，最后分析它们的局限'));
    expect(state.startOperation).toHaveBeenCalledWith('task', expect.objectContaining({ kind: 'conversation.execute', input: expect.objectContaining({
      capability: 'compose', steps: ['background', 'compare', 'critique'], allowedPaperIds: ['a', 'b'],
    }) }));
    expect(state.task.activeActivity.id).toBe('lesson');
  });

  it('carries a selected critique issue and saved version into a scoped followup without generating on selection', async () => {
    const critique = { schemaVersion: 2, scope: { allowedPaperIds: ['a'] }, presentation: { chatIssueIds: ['i1', 'i2'] } };
    state.task.messages = [{ id: 'critique-message', role: 'ai', artifactId: 'critique-artifact', content: '两点判断', critique }];
    state.task.artifacts = [{ id: 'critique-artifact', title: '批判成果', text: '用户编辑后的正文', paperIds: ['a'], updatedAt: 'saved-token', edited: true, critique }];
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onFollowupIssue(state.task.messages[0], 'i2'));
    expect(state.startOperation).not.toHaveBeenCalled();
    expect(screen.getByText(/正在追问/u)).toBeInTheDocument();
    expect(screen.queryByText(/保存于 saved-token/u)).not.toBeInTheDocument();
    await act(async () => state.chatProps.onSendMessage('展开实验条件'));
    expect(state.startOperation).toHaveBeenCalledWith('task', expect.objectContaining({ kind: 'conversation.execute', input: expect.objectContaining({
      followup: { artifactId: 'critique-artifact', issueId: 'i2', version: 'saved-token' }, allowedPaperIds: ['a'],
    }) }));
  });

  it('prepares regeneration with the original question, target and saved version without calling the model', async () => {
    const critique = { schemaVersion: 2, question: { original: '只检查质量主张' },
      scope: { allowedPaperIds: ['a'], targetPaperIds: ['a'] } };
    state.task.artifacts = [{ id: 'critique-artifact', title: '批判成果', text: '原成果', paperIds: ['a'], updatedAt: 'saved-token', critique }];
    render(<UnifiedTaskApp />);
    fireEvent.click(screen.getByRole('button', { name: '批判成果 · 成果' }));
    fireEvent.click(screen.getByRole('button', { name: '成果更多操作' }));
    fireEvent.click(screen.getByRole('button', { name: '重新核查', exact: true }));
    expect(state.startOperation).not.toHaveBeenCalled();
    expect(screen.getByText(/重新核查 批判成果/u)).toBeInTheDocument();
    await act(async () => state.chatProps.onSendMessage('/批判 只检查质量主张'));
    expect(state.startOperation).toHaveBeenCalledWith('task', expect.objectContaining({ input: expect.objectContaining({
      capability: 'critique', targetPaperIds: ['a'], followup: { artifactId: 'critique-artifact', version: 'saved-token', regenerate: true },
    }) }));
  });
  it('blocks a stale chat issue after regeneration without sending a model request', async () => {
    const critique = { schemaVersion: 2, presentation: { chatIssueIds: ['i1'] } };
    state.task.messages = [{ role: 'ai', artifactId: 'a1', sourceRequestId: 'old', critique }];
    state.task.artifacts = [{ id: 'a1', title: '新版成果', paperIds: ['a'], updatedAt: 'new-version', sourceRequestId: 'new', critique }];
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onFollowupIssue(state.task.messages[0], 'i1'));
    expect(screen.getByText(/这条回答对应旧版本/u)).toBeInTheDocument();
    await act(async () => state.chatProps.onSendMessage('第一点为什么'));
    expect(state.startOperation).not.toHaveBeenCalled();
  });

  it('clarifies vague analysis without a model call and uses the selected capability', async () => {
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onSendMessage('帮我分析一下'));
    expect(screen.getByRole('group', { name: '选择分析重点' })).toBeInTheDocument();
    expect(state.startOperation).not.toHaveBeenCalled();
    expect(state.writes).toBe(0);
    fireEvent.click(screen.getByRole('button', { name: '概括与解释' }));
    await waitFor(() => expect(state.startOperation).toHaveBeenCalledWith('task', expect.objectContaining({ input: expect.objectContaining({
      capability: 'chat', displayText: '帮我分析一下', allowedPaperIds: ['a', 'b'],
    }) })));
  });

  it('uses task material for an unspecified critique and reader focus only for an explicit single-paper reference', async () => {
    state.task.focusedPaperId = 'a';
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onSendMessage('/批判 检查论证依据'));
    expect(state.startOperation.mock.calls[0][1].input.allowedPaperIds).toEqual(['a', 'b']);
    await act(async () => state.chatProps.onSendMessage('/批判 检查这篇论文的论证依据'));
    expect(state.startOperation.mock.calls[1][1].input).toMatchObject({ allowedPaperIds: ['a', 'b'], primaryPaperId: 'a' });
  });

  it('queries durable material state after opening a task and blocks unready evidence before model execution', async () => {
    materialProcessing.mockImplementation(async (taskId, paperId) => ({
      status: 'success', pdfId: paperId, readingReady: true, questionReady: false,
      processingStatus: 'failed', aiAnalysisStatus: 'not_requested',
    }));
    render(<UnifiedTaskApp />);
    await waitFor(() => expect(state.chatProps.materials.find(item => item.id === 'b')?.questionReady).toBe(false));
    await act(async () => state.chatProps.onSendMessage('只根据 @{b} 解释方法'));
    expect(materialProcessing).toHaveBeenCalledWith('task', 'b');
    expect(state.startOperation).not.toHaveBeenCalled();
    expect(screen.getByText(/正文尚未就绪/)).toBeInTheDocument();
  });

  it('uses named material instead of the active lesson and filters old history', async () => {
    state.task.messages = [{ role: 'ai', content: 'A secret', context: { taskId: 'task', allowedPaperIds: ['a'] } }];
    render(<UnifiedTaskApp />);
    await waitFor(() => expect(screen.getByText('论文乙')).toBeInTheDocument());
    await act(async () => state.chatProps.onSendMessage('只根据《论文乙》解释方法'));
    expect(state.startOperation.mock.calls[0][1].input).toMatchObject({ allowedPaperIds: ['b'], primaryPaperId: 'b', strictScope: true });
    expect(state.startOperation.mock.calls[0][1].input).not.toHaveProperty('history');
  });

  it('lets an explicit different paper leave an active lesson without replacing it', async () => {
    state.task.activeActivity = { activityId: 'lesson', status: 'active', pdfId: 'a', paperIds: ['a'], primaryPaperId: 'a' };
    render(<UnifiedTaskApp />);
    await waitFor(() => expect(screen.getByText('论文乙')).toBeInTheDocument());
    await act(async () => state.chatProps.onSendMessage('只根据 @{b} 解释方法'));
    expect(state.startOperation.mock.calls[0][1].input).toMatchObject({ allowedPaperIds: ['b'], strictScope: true });
    expect(state.task.activeActivity.pdfId).toBe('a');
  });

  it('rejects an unknown slash command before invoking or saving a model request', async () => {
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onSendMessage('/未知 帮我看看'));
    expect(state.api.sendTaskMessage).not.toHaveBeenCalled();
    expect(state.writes).toBe(0);
    expect(screen.getByText(/未识别这个命令/)).toBeInTheDocument();
  });

  it('keeps chat citations when a background request cannot use the direct paper endpoint', async () => {
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onSendMessage('/补课 解释这个术语'));
    expect(state.api.backgroundKnowledge).not.toHaveBeenCalled();
    expect(state.task.messages.at(-1).sentenceSourceMap).toEqual([{ target: 'message', sentence: '回答', sourceIds: ['s'] }]);
  });

  it('recovers a usable pane when a stored layout hides both main panes', async () => {
    localStorage.setItem('pixiu-unified-layout-v1', JSON.stringify({ reader: false, chat: false }));
    render(<UnifiedTaskApp />);
    expect(screen.getByRole('region', { name: '论文与成果' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '展开对话区' })).toBeInTheDocument();
  });
  it('retains the request identity when adopting a confirmed result fails locally', async () => {
    state.failAnswerSave = true;
    render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onSendMessage('解释这个术语'));
    expect(state.writes).toBe(0);
    expect(localStorage.getItem('pixiu-task-request-v1:' + state.startOperation.mock.calls[0][1].requestId)).not.toBeNull();
    expect(state.chatProps.isLoading).toBe(true);
  });
  it('opens results for reading and preserves edits when switching views without saving', async () => {
    state.task.notes = [{ id: 'note', title: '阅读笔记', text: '**已保存正文**' }];
    render(<UnifiedTaskApp />);
    fireEvent.click(screen.getByRole('button', { name: '阅读笔记 · 笔记', exact: true }));
    expect(screen.getByRole('article', { name: '成果正文' })).toHaveTextContent('已保存正文');
    expect(screen.queryByRole('textbox', { name: '编辑笔记与成果' })).not.toBeInTheDocument();
    expect(screen.queryByText('已保存', { exact: true })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '编辑', exact: true }));
    expect(screen.getByRole('button', { name: '保存', exact: true })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '编辑笔记与成果' }), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: '完成编辑', exact: true }));
    expect(screen.getByRole('article', { name: '成果正文' })).toHaveTextContent('（空白正文）');
    expect(screen.getByText('未保存修改')).toBeInTheDocument();
    expect(state.task.notes[0].text).toBe('**已保存正文**');
    expect(state.writes).toBe(0);
    fireEvent.click(screen.getByRole('button', { name: '编辑', exact: true }));
    expect(screen.getByRole('textbox', { name: '编辑笔记与成果' })).toHaveValue('');
  });

  it('keeps the loaded PDF mounted and preserves its page while reading a saved result', async () => {
    state.task.focusedPaperId = 'a';
    state.task.notes = [{id: 'note', title: '阅读笔记', text: '已保存正文'}];
    localDbGet.mockImplementation(async store => store === 'pdfStore' ? new Blob(['fixture'])
      : store === 'deconstructStore' ? {pdfId: 'a'} : null);
    const makeUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:paper');
    const releaseUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const view = render(<UnifiedTaskApp />);
    await screen.findByTestId('paper-viewer');
    act(() => state.pdfProps.onPageChange({pageIndex: 6, totalPages: 19}));
    expect(screen.getByRole('textbox', {name: '跳转到页码'})).toHaveValue('7');
    fireEvent.click(screen.getByRole('button', {name: '阅读笔记 · 笔记', exact: true}));
    expect(screen.getByTestId('paper-viewer')).not.toBeVisible();
    const retainedPaper = screen.getByTestId('paper-viewer').closest('.unified-reader-paper');
    expect(retainedPaper).toHaveStyle({visibility: 'hidden'});
    expect(retainedPaper.style.display).not.toBe('none');
    expect(retainedPaper).toHaveAttribute('inert');
    expect(retainedPaper.querySelector('[aria-label="论文页码"]')).not.toBeNull();
    // A layout observer in the hidden viewer must not overwrite visible position.
    act(() => state.pdfProps.onPageChange({pageIndex: 0, totalPages: 20}));
    fireEvent.click(screen.getByRole('button', {name: '查看原文', exact: true}));
    expect(screen.getByTestId('paper-viewer')).toBeVisible();
    expect(screen.getByRole('textbox', {name: '跳转到页码'})).toHaveValue('7');
    expect(screen.getByRole('form',{name:'论文页码'})).toHaveTextContent('/ 20 页');
    expect(state.pdfProps.active).toBe(true);
    expect(state.pdfProps.readingKey).toBe('task:a');
    expect(state.pdfMounts).toBe(1);
    expect(state.pdfUnmounts).toBe(0);
    expect(state.startOperation).not.toHaveBeenCalled();
    view.unmount();
    makeUrl.mockRestore(); releaseUrl.mockRestore();
  });

  it('isolates source jumps from other papers and expires them on manual navigation', async () => {
    state.task.focusedPaperId = 'a';
    localStorage.setItem('pixiu-reading-position:["task","b"]', '6');
    localDbGet.mockImplementation(async store => store === 'pdfStore' ? new Blob(['fixture']) : store === 'deconstructStore' ? {pdfId: 'a'} : null);
    const makeUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:paper');
    const releaseUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const view = render(<UnifiedTaskApp />);
    await screen.findByTestId('paper-viewer');
    await act(async () => state.chatProps.onJumpToSource({ pdfId: 'a', pageIndex: 3, sectionId: 'evidence' }));
    expect(state.pdfProps.targetPageJumpToken).toBeGreaterThan(0);
    expect(state.pdfProps.focusedSourceAnchorId).toBe('evidence');
    fireEvent.click(screen.getByRole('button', { name: '论文乙', exact: true }));
    view.rerender(<UnifiedTaskApp />);
    await waitFor(() => expect(state.pdfProps.pdfId).toBe('b'));
    expect(state.pdfProps.targetPageIndex).toBe(6);
    expect(state.pdfProps.targetPageJumpToken).toBe(0);
    expect(state.pdfProps.focusedSourceAnchorId).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '论文甲', exact: true }));
    view.rerender(<UnifiedTaskApp />);
    await waitFor(() => expect(state.pdfProps.pdfId).toBe('a'));
    expect(state.pdfProps.targetPageJumpToken).toBe(0);
    expect(state.pdfProps.focusedSourceAnchorToken).toBe(0);
    expect(state.startOperation).not.toHaveBeenCalled();
    view.unmount(); makeUrl.mockRestore(); releaseUrl.mockRestore();
  });

  it('keeps completed learning in the task navigation and restores the last opened record after refresh', async () => {
    state.task.activeActivity = { activityId: 'finished', pdfId: 'a', status: 'finished', mode: 'read',
      concepts: [{ id: 'c', question: '压缩会丢失什么？', status: 'skipped' }], turns: [] };
    const view = render(<UnifiedTaskApp />);
    await act(async () => {});
    expect(screen.getByRole('region', { name: '任务对话' }).querySelector('.unified-learning-history')).toBeNull();
    fireEvent.click(screen.getByText('学习记录（1）'));
    fireEvent.click(screen.getByRole('button', { name: '精读 · 论文甲：压缩会丢失什么 · 已结束' }));
    expect(screen.getByRole('article', { name: '学习记录详情' })).toHaveTextContent('已跳过');
    expect(screen.getByRole('article', { name: '学习记录详情' })).not.toHaveTextContent('已掌握');
    view.unmount();
    render(<UnifiedTaskApp />);
    await waitFor(() => expect(screen.getByRole('article', { name: '学习记录详情' })).toHaveTextContent('压缩会丢失什么'));
    expect(state.startOperation).not.toHaveBeenCalled();
  });

  it('restores a document draft and scroll position across evidence navigation and refresh', async () => {
    state.task.focusedPaperId = 'a';
    state.task.notes = [{ id: 'n', title: '实验笔记', text: '原正文' }];
    const view = render(<UnifiedTaskApp />);
    fireEvent.click(screen.getByRole('button', { name: '实验笔记 · 笔记' }));
    fireEvent.click(screen.getByRole('button', { name: '编辑', exact: true }));
    fireEvent.change(screen.getByRole('textbox', { name: '编辑笔记与成果' }), { target: { value: '未保存的实验想法' } });
    const panel = screen.getByRole('textbox', { name: '编辑笔记与成果' }).closest('.unified-document');
    fireEvent.scroll(panel, { target: { scrollTop: 135 } });
    let liveScrollTop = 135;
    Object.defineProperty(panel, 'scrollTop', {
      configurable: true,
      get() { return this.isConnected ? liveScrollTop : 0; },
      set(value) { liveScrollTop = value; },
    });
    await act(async () => state.chatProps.onJumpToSource({ pdfId: 'a', pageIndex: 3 }));
    fireEvent.click(screen.getByRole('button', { name: '返回笔记' }));
    expect(screen.getByRole('article', { name: '成果正文' })).toHaveTextContent('未保存的实验想法');
    expect(screen.getByRole('article', { name: '成果正文' }).closest('.unified-document').scrollTop).toBe(135);
    view.unmount();
    render(<UnifiedTaskApp />);
    await waitFor(() => expect(screen.getByRole('article', { name: '成果正文' })).toHaveTextContent('未保存的实验想法'));
    expect(state.task.notes[0].text).toBe('原正文');
    expect(state.writes).toBe(0);
  });

  it('saves the same answer once without interrupting reading and opens it only on request', async () => {
    state.task.focusedPaperId = 'a';
    state.task.messages = [{ id: 'answer', role: 'ai', content: '同一份回答', context: { allowedPaperIds: ['a'] } }];
    const view = render(<UnifiedTaskApp />);
    await act(async () => state.chatProps.onCaptureArtifact(0));
    view.rerender(<UnifiedTaskApp />);
    await act(async () => state.chatProps.onCaptureArtifact(0));
    expect(state.task.artifacts).toHaveLength(1);
    expect(state.task.messages[0].artifactId).toBe(state.task.artifacts[0].id);
    expect(screen.queryByRole('article', { name: '成果正文' })).not.toBeInTheDocument();
    expect(state.task.focusedPaperId).toBe('a');
    await act(async () => state.chatProps.onOpenArtifact(state.task.artifacts[0].id));
    expect(screen.getByRole('article', { name: '成果正文' })).toHaveTextContent('同一份回答');
  });

  it('keeps ordinary chat distinct from answering an active learning question', async () => {
    state.task.focusedPaperId = 'a';
    state.task.activeActivity = { activityId: 'lesson', pdfId: 'a', paperIds: ['a'], primaryPaperId: 'a', status: 'active', concepts: [{ id: 'c', status: 'pending' }] };
    render(<UnifiedTaskApp />);
    expect(state.chatProps.sendLabel).toBe('发送消息');
    fireEvent.click(screen.getByRole('button', { name: '回答这道题' }));
    expect(state.chatProps.sendLabel).toBe('提交回答');
    fireEvent.click(screen.getByRole('button', { name: '改为普通提问' }));
    await act(async () => state.chatProps.onSendMessage('解释一下这篇论文'));
    expect(state.startOperation).toHaveBeenCalledWith('task', expect.objectContaining({ kind: 'conversation.execute', input: expect.objectContaining({ capability: 'chat' }) }));
  });

  it('automatically translates on entering translated or comparison views and deduplicates switching', async () => {
    state.realTranslation = true;
    state.task.focusedPaperId = 'a';
    let finish;
    state.translatePage = vi.fn(() => new Promise(resolve => { finish = resolve; }));
    localDbGet.mockImplementation(async store => store === 'pdfStore' ? new Blob(['fixture']) : store === 'deconstructStore' ? { pdfId: 'a' } : null);
    const makeUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:automatic-translation');
    const releaseUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const view = render(<UnifiedTaskApp />);
    await screen.findByTestId('paper-viewer');
    await act(async () => state.pdfProps.onPageTextExtracted({ pageIndex: 0, pageText: 'This is a local fixture page.' }));
    expect(state.translatePage).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '译文', exact: true }));
    await waitFor(() => expect(state.translatePage).toHaveBeenCalledTimes(1));
    expect(state.translationPanelProps.pageData.status).toBe('loading');
    fireEvent.click(screen.getByRole('button', { name: '对照', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: '原文', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: '译文', exact: true }));
    expect(state.translatePage).toHaveBeenCalledTimes(1);
    await act(async () => state.translationPanelProps.onCancel());
    expect(state.translatePage.mock.calls[0][5].signal.aborted).toBe(true);
    await act(async () => finish({ translatedText: '迟到的结果' }));
    expect(state.translationPanelProps.pageData.status).toBe('cancelled');
    fireEvent.click(screen.getByRole('button', { name: '对照', exact: true }));
    expect(state.translatePage).toHaveBeenCalledTimes(1);
    let retry;
    act(() => { retry = state.translationPanelProps.onRetry(); });
    expect(state.translatePage).toHaveBeenCalledTimes(2);
    await act(async () => { finish({ translatedText: '本地测试译文' }); await retry; });
    expect(state.translationPanelProps.pageData.translatedText).toBe('本地测试译文');
    fireEvent.click(screen.getByRole('button', { name: '原文', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: '对照', exact: true }));
    expect(state.translatePage).toHaveBeenCalledTimes(2);
    view.unmount(); makeUrl.mockRestore(); releaseUrl.mockRestore();
  });

  it('submits an explicit learning answer only to its activity and shows ordinary sending for other material', async () => {
    state.task.focusedPaperId = 'a';
    state.task.activeActivity = { activityId: 'lesson', pdfId: 'a', paperIds: ['a'], primaryPaperId: 'a', status: 'active', revision: 2, concepts: [{ id: 'c', status: 'pending' }] };
    state.task.messages = [{ id: 'question', role: 'ai', content: '压缩可能损失什么？', context: { activityId: 'lesson' } }, { id: 'ordinary', role: 'ai', content: '普通解释' }];
    render(<UnifiedTaskApp />);
    expect(screen.getAllByRole('group', { name: '学习问题操作' })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: '回答这道题' }));
    await act(async () => state.chatProps.onDraftChange('解释 @{论文乙}'));
    expect(state.chatProps.sendLabel).toBe('发送消息');
    await act(async () => state.chatProps.onDraftChange('/比较 两篇论文'));
    expect(state.chatProps.sendLabel).toBe('发送消息');
    await act(async () => state.chatProps.onDraftChange('剪枝删除冗余高斯'));
    expect(state.chatProps.sendLabel).toBe('提交回答');
    await act(async () => state.chatProps.onSendMessage('剪枝删除冗余高斯'));
    expect(state.startOperation).toHaveBeenCalledWith('task', expect.objectContaining({ kind: 'learning.action', input: expect.objectContaining({ action: 'answer', activityId: 'lesson', text: '剪枝删除冗余高斯' }) }));
    await waitFor(() => expect(state.chatProps.sendLabel).toBe('发送消息'));
  });

  it('cleans visible questions while retaining explicitly selected scope in execution', async () => {
    state.task.activeActivity = null;
    render(<UnifiedTaskApp />);
    await waitFor(() => expect(state.chatProps.materials.find(item => item.id === 'b')?.title).toBe('论文乙'));
    await act(async () => state.chatProps.onSendMessage('解释方法 @{论文乙}'));
    expect(state.startOperation.mock.calls[0][1].input).toMatchObject({ displayText: '解释方法', allowedPaperIds: ['b'] });
    expect(state.task.messages.find(item => item.role === 'user').content).toBe('解释方法');
  });

  it('adapts beginner choices to the task and opens paper selection without generating', async () => {
    state.task.activeActivity = null;
    const view = render(<UnifiedTaskApp />);
    expect(state.chatProps.starterPrompts[0].label).toBe('先选择要读的论文');
    await act(async () => state.chatProps.starterPrompts[0].onSelect());
    expect(state.startOperation).not.toHaveBeenCalled();
    state.task = { ...state.task, focusedPaperId: 'b' };
    view.rerender(<UnifiedTaskApp />);
    expect(state.chatProps.starterPrompts[0].label).toBe('先看懂这篇论文');
    state.task = { ...state.task, paperIds: [], focusedPaperId: null };
    view.rerender(<UnifiedTaskApp />);
    expect(state.chatProps.starterPrompts[0].label).toBe('解释一个概念');
    expect(state.startOperation).not.toHaveBeenCalled();
  });

  it('binds a saved answer to its identity when an earlier message was removed before persistence', async () => {
    state.task.messages = [{ id: 'first', role: 'user', content: '旧问题' }, { id: 'answer', role: 'ai', content: '要保存的回答' }];
    render(<UnifiedTaskApp />);
    state.beforeUpdate = () => { state.task = { ...state.task, messages: state.task.messages.slice(1) }; };
    await act(async () => state.chatProps.onCaptureArtifact(1));
    expect(state.task.messages).toEqual([expect.objectContaining({ id: 'answer', artifactId: state.task.artifacts[0].id })]);
    expect(state.task.artifacts[0].text).toBe('要保存的回答');
  });

  it('keeps ten completed activities available in navigation without occupying the current activity bar', async () => {
    state.task.activeActivity = null;
    state.task.activityHistory = Array.from({ length: 10 }, (_, index) => ({ activityId: `ended-${index}`, mode: 'read', status: 'finished', pdfId: 'a', concepts: [{ question: `历史问题${index}`, status: 'skipped' }] }));
    render(<UnifiedTaskApp />);
    await act(async () => {});
    expect(screen.queryByLabelText('当前活动')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: '任务对话' })).not.toHaveTextContent('历史问题');
    fireEvent.change(screen.getByRole('textbox', { name: '搜索材料与记录' }), { target: { value: '历史问题9' } });
    fireEvent.click(screen.getByRole('button', { name: '精读 · 论文甲：历史问题9 · 已结束' }));
    expect(screen.getByRole('article', { name: '学习记录详情' })).toHaveTextContent('历史问题9');
    expect(state.startOperation).not.toHaveBeenCalled();
  });

  it('prioritizes running research over an older paused run and stops the displayed run', async () => {
    state.task.activeActivity = null;
    state.task.researchRuns = ['paused-old', 'running-new'].map(researchId => ({ researchId, requestId: researchId, question: researchId, paperIds: ['a'] }));
    state.researchGet.mockImplementation(async (_, id) => ({ task: { taskId: id, status: id === 'paused-old' ? 'paused' : 'running' } }));
    state.researchAction.mockImplementation(async (_, id) => ({ task: { taskId: id, status: 'cancelled' } }));
    render(<UnifiedTaskApp />);
    const activity = await screen.findByLabelText('当前活动');
    await waitFor(() => expect(within(activity).getAllByRole('button')[0]).toHaveTextContent('研究 · 进行中'));
    fireEvent.click(within(activity).getByText('另有 1 项'));
    expect(within(activity).getByRole('button', { name: '研究 · 已暂停 · 查看' })).toBeVisible();
    fireEvent.click(within(activity).getByRole('button', { name: '停止研究' }));
    await waitFor(() => expect(state.researchAction).toHaveBeenCalledWith('task', 'running-new', 'cancel', undefined));
    await waitFor(() => expect(within(activity).getAllByRole('button')[0]).toHaveTextContent('研究 · 已暂停'));
  });

  it('reuses the same page translation and preserves revisions only when its content changes', async () => {
    state.task.focusedPaperId = 'a';
    localDbGet.mockImplementation(async store => store === 'pdfStore' ? new Blob(['fixture']) : store === 'deconstructStore' ? { pdfId: 'a' } : null);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:translation');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const view = render(<UnifiedTaskApp />);
    await screen.findByTestId('paper-viewer');
    fireEvent.click(screen.getByRole('button', { name: '译文', exact: true }));
    await act(async () => state.translationPanelProps.onCaptureArtifact({ text: '第一页译文' }));
    view.rerender(<UnifiedTaskApp />);
    await act(async () => state.translationPanelProps.onCaptureArtifact({ text: '第一页译文' }));
    await act(async () => state.translationPanelProps.onCaptureArtifact({ text: '修订后的译文' }));
    expect(state.task.artifacts).toHaveLength(1);
    expect(state.task.artifacts[0]).toMatchObject({ type: 'translation', text: '修订后的译文', pageIndex: 0 });
    expect(state.task.artifacts[0].versions).toHaveLength(1);
    expect(state.task.artifacts[0].versions[0].text).toBe('第一页译文');
    vi.restoreAllMocks();
  });

  it('keeps keyboard focus in processing history and returns it to its opener', async () => {
    render(<UnifiedTaskApp />);
    const opener = screen.getByRole('button', { name: '切换任务' });
    fireEvent.click(opener);
    fireEvent.click(screen.getByRole('button', { name: '处理记录', exact: true }));
    const close = screen.getByRole('button', { name: '关闭', exact: true });
    expect(close).toHaveFocus();
    const last = screen.getByRole('combobox', { name: '处理状态筛选' });
    last.focus(); fireEvent.keyDown(last, { key: 'Tab' });
    expect(close).toHaveFocus();
    fireEvent.keyDown(close, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '处理记录' })).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('stops the running research from the current activity bar without starting a new model request', async () => {
    state.task.researchRuns = [{ researchId: 'r', requestId: 'start-r', question: '实验方案', paperIds: ['a'] }];
    state.researchGet.mockResolvedValue({ task: { taskId: 'r', status: 'running' } });
    state.researchAction.mockResolvedValue({ task: { taskId: 'r', status: 'cancelled' } });
    render(<UnifiedTaskApp />);
    fireEvent.click(await screen.findByRole('button', { name: '停止研究', exact: true }));
    await waitFor(() => expect(state.researchAction).toHaveBeenCalledWith('task', 'r', 'cancel', undefined));
    await waitFor(() => expect(screen.queryByRole('button', { name: '停止研究', exact: true })).not.toBeInTheDocument());
    expect(state.researchAction).toHaveBeenCalledTimes(1);
    expect(state.startOperation).not.toHaveBeenCalled();
  });

  it('restores unsaved note edits after leaving the editor, including an intentionally empty draft', async () => {
    state.task.focusedPaperId = 'a';
    state.task.notes = [{ id: 'note', title: '我的笔记', text: '已保存正文' }];
    render(<UnifiedTaskApp />);
    fireEvent.click(screen.getByRole('button', { name: '我的笔记 · 笔记' }));
    fireEvent.click(screen.getByRole('button', { name: '编辑', exact: true }));
    fireEvent.change(screen.getByRole('textbox', { name: '编辑笔记与成果' }), { target: { value: '尚未提交的修改' } });
    fireEvent.click(screen.getByRole('button', { name: '查看原文' }));
    fireEvent.click(screen.getByRole('button', { name: '我的笔记 · 笔记' }));
    fireEvent.click(screen.getByRole('button', { name: '编辑', exact: true }));
    expect(screen.getByRole('textbox', { name: '编辑笔记与成果' })).toHaveValue('尚未提交的修改');
    fireEvent.change(screen.getByRole('textbox', { name: '编辑笔记与成果' }), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: '查看原文' }));
    fireEvent.click(screen.getByRole('button', { name: '我的笔记 · 笔记' }));
    fireEvent.click(screen.getByRole('button', { name: '编辑', exact: true }));
    expect(screen.getByRole('textbox', { name: '编辑笔记与成果' })).toHaveValue('');
    expect(state.task.notes[0].text).toBe('已保存正文');
  });
  it('restores a historical note through persistence and shows the restored text in the editor', async () => {
    state.task.notes = [{ id: 'note', title: '版本笔记', text: '当前正文', versions: [{ text: '先前正文', savedAt: '2026-10-04' }] }];
    render(<UnifiedTaskApp />);
    fireEvent.click(screen.getByRole('button', { name: '版本笔记 · 笔记' }));
    fireEvent.click(screen.getByRole('button', { name: '编辑', exact: true }));
    fireEvent.change(screen.getByRole('textbox', { name: '编辑笔记与成果' }), { target: { value: '未保存修改' } });
    fireEvent.click(screen.getByRole('button', { name: '笔记更多操作' }));
    fireEvent.click(screen.getByText('历史版本（1）'));
    fireEvent.change(screen.getByLabelText('选择历史版本'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: '恢复这个版本' }));
    await waitFor(() => expect(screen.getByRole('textbox', { name: '编辑笔记与成果' })).toHaveValue('先前正文'));
    expect(state.task.notes[0].text).toBe('先前正文');
    expect(state.task.notes[0].versions.map((item) => item.text)).toEqual(['先前正文', '当前正文', '未保存修改']);
  });
  it('saves the selected user message as its own note without previous answer metadata', async () => {
    state.task.messages = [
      { id: 'previous', role: 'user', content: '剪枝的贡献怎么体现 真的有贡献吗' },
      { id: 'answer', role: 'ai', content: '上一轮回答', rag_sources: [{ pdfId: 'a', text: '上一轮证据' }] },
      { id: 'current', role: 'user', content: '什么是lightgaussian', capability: 'critique', context: { allowedPaperIds: ['a', 'b'] }, rag_sources: [{ pdfId: 'a', text: '错误继承的证据' }] },
    ];
    const view = render(<UnifiedTaskApp />);
    await act(async () => state.chatProps.onSaveToNote(2));
    view.rerender(<UnifiedTaskApp />);
    expect(state.task.notes).toHaveLength(1);
    expect(state.task.notes[0]).toMatchObject({ title: '什么是lightgaussian', text: '什么是lightgaussian', type: 'note', sourceMessageId: 'current', sources: [], paperIds: [], sentenceSourceMap: [] });
    expect(state.task.notes[0].capability).toBeUndefined();
    expect(state.task.artifacts).toHaveLength(0);
    expect(screen.queryByRole('article', { name: '成果正文' })).not.toBeInTheDocument();
    await act(async () => state.chatProps.onOpenArtifact(state.task.notes[0].id));
    expect(screen.getByRole('article', { name: '成果正文' })).toHaveTextContent('什么是lightgaussian');
    expect(screen.queryByText(/证据片段/u)).not.toBeInTheDocument();
    await act(async () => state.chatProps.onSaveToNote(2));
    expect(state.task.notes).toHaveLength(1);
  });

  it('preserves evidence when capturing a conversation as a note', async () => {
    const source = { sourceId: 'evidence', pdfId: 'b', pageIndex: 3, text: 'original evidence' };
    state.task.messages = [{ id: 'message', role: 'ai', content: '结论', rag_sources: [source], context: { allowedPaperIds: ['b'] } }];
    const view = render(<UnifiedTaskApp />);
    await screen.findByTestId('chat');
    await act(async () => state.chatProps.onSaveToNote(0));
    expect(state.task.notes[0].sources).toEqual([source]);
    expect(state.task.notes[0].paperIds).toEqual(['b']);
    view.rerender(<UnifiedTaskApp />);
    await act(async () => state.chatProps.onOpenArtifact(state.task.notes[0].id));
    expect(screen.getByText('证据片段（1）')).toBeInTheDocument();
  });

  it('retains an explicit quotation when saving the first user message', async () => {
    state.task.messages = [{ id: 'first', role: 'user', content: '我的摘录想法\n补充说明', sourceAnchorId: 'quote', sourcePdfId: 'b', sourcePageIndex: 3, sourceText: '原文摘录' }];
    render(<UnifiedTaskApp />);
    await act(async () => state.chatProps.onSaveToNote(0));
    expect(state.task.notes[0]).toMatchObject({ title: '我的摘录想法', text: '我的摘录想法\n补充说明', paperIds: ['b'], sources: [{ sourceId: 'quote', pdfId: 'b', pageIndex: 3, text: '原文摘录' }] });
  });

  it('blocks an old editor draft even after background refresh adopts the newer task revision', async () => {
    state.task.focusedPaperId = 'a';
    state.task.notes = [{ id: 'note', title: '并发笔记', text: '原正文' }];
    const view = render(<UnifiedTaskApp />);
    fireEvent.click(screen.getByRole('button', { name: '并发笔记 · 笔记', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: '编辑', exact: true }));
    fireEvent.change(screen.getByRole('textbox', { name: '编辑笔记与成果' }), { target: { value: '我的旧草稿' } });
    state.task = { ...state.task, revision: 10, notes: [{ id: 'note', title: '并发笔记', text: '另一客户端的新正文' }] };
    view.rerender(<UnifiedTaskApp />);
    fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
    await waitFor(() => expect(state.retainDraft).toHaveBeenCalledWith(expect.objectContaining({ notes: [expect.objectContaining({ text: '我的旧草稿' })] }), 'document-conflict'));
    expect(state.task.notes[0].text).toBe('另一客户端的新正文');
    expect(state.writes).toBe(0);
    fireEvent.click(screen.getByRole('button', { name: '查看原文', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: '并发笔记 · 笔记', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: '编辑', exact: true }));
    expect(screen.getByRole('textbox', { name: '编辑笔记与成果' })).toHaveValue('我的旧草稿');
    expect(screen.getByRole('button', { name: '已核对，保留我的修改', exact: true })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '已核对，保留我的修改', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
    await waitFor(() => expect(state.task.notes[0].text).toBe('我的旧草稿'));
    expect(state.task.notes[0].versions[0].text).toBe('另一客户端的新正文');
  });
});
