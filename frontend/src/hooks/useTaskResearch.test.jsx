import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useTaskResearch } from './useTaskResearch';

describe('task research integration', () => {
  it('prioritizes the visible newest run without waiting for slow history and bounds concurrency', async () => {
    const old = { id: 'old', researchRuns: [{ researchId: 'old-run' }] };
    const active = { id: 'active', researchRuns: ['r1', 'r2', 'r3', 'r4'].map(researchId => ({ researchId })) };
    const pending = new Map();
    const api = { get: vi.fn((_taskId, researchId) => new Promise(resolve => pending.set(researchId, resolve))) };
    const workspace = { tasks: [old, active], activeTaskId: 'active', adoptServerTask: vi.fn() };
    const { result, unmount } = renderHook(() => useTaskResearch(workspace, api));
    expect(api.get.mock.calls).toEqual([['active', 'r4'], ['active', 'r3'], ['active', 'r2']]);
    await act(async () => pending.get('r4')({ task: { taskId: 'r4', status: 'running' } }));
    expect(result.current.runs['active/r4'].status).toBe('running');
    expect(api.get.mock.calls).toHaveLength(4);
    expect(api.get.mock.calls[3]).toEqual(['active', 'r1']);
    unmount();
    await act(async () => {
      for (const [id, resolve] of pending) resolve({ task: { taskId: id, status: 'running' } });
    });
    expect(api.get.mock.calls).toHaveLength(4);
  });

  it('does not restart in-flight reads when server publication reorders tasks', async () => {
    const a = { id: 'a', researchRuns: [{ researchId: 'ra' }] };
    const b = { id: 'b', researchRuns: [{ researchId: 'rb' }] };
    const pending = new Map();
    const api = { get: vi.fn((_taskId, id) => new Promise(resolve => pending.set(id, resolve))) };
    const workspace = { tasks: [a, b], activeTaskId: 'a', adoptServerTask: vi.fn() };
    const { result, rerender, unmount } = renderHook(({ current }) => useTaskResearch(current, api),
      { initialProps: { current: workspace } });
    rerender({ current: { ...workspace, tasks: [b, a] } });
    expect(api.get).toHaveBeenCalledTimes(2);
    await act(async () => pending.get('ra')({ task: { taskId: 'ra', status: 'running' } }));
    expect(result.current.runs['a/ra'].status).toBe('running');
    unmount();
    await act(async () => pending.get('rb')({ task: { taskId: 'rb', status: 'running' } }));
    expect(result.current.runs['b/rb']).toBeUndefined();
  });

  it('stops polling missing historical execution records', async () => {
    vi.useFakeTimers();
    try {
      const task = { id: 't', researchRuns: [{ researchId: 'missing' }] };
      const api = { get: vi.fn().mockRejectedValue({ response: { status: 404 } }) };
      const hook = renderHook(() => useTaskResearch({ tasks: [task] }, api));
      await act(async () => {});
      await act(async () => vi.advanceTimersByTimeAsync(16000));
      expect(api.get).toHaveBeenCalledTimes(1);
      expect(hook.result.current.error).toContain('执行记录当前不可用');
      hook.unmount();
    } finally { vi.useRealTimers(); }
  });
  it('freezes a fresh-material continuation revision across an uncertain response and reload', async () => {
    const task = { id: 'followup-intent', revision: 4, researchRuns: [] };
    const current = { tasks: [task], adoptServerTask: vi.fn() };
    const api = { action: vi.fn().mockRejectedValue(new Error('返回未确认')) };
    const payload = { requestId: 'same-followup', expectedRunRevision: 7,
      materialSelection: { mode: 'task_default' }, question: '使用新论文补查' };
    const first = renderHook(() => useTaskResearch(current, api));
    await act(async () => { await expect(first.result.current.action(task.id, 'parent', 'continue', payload)).rejects.toThrow('返回未确认'); });
    first.unmount();
    const second = renderHook(() => useTaskResearch({ ...current, tasks: [{ ...task, revision: 9 }] }, api));
    await act(async () => { await expect(second.result.current.action(task.id, 'parent', 'continue', payload)).rejects.toThrow('返回未确认'); });
    expect(api.action.mock.calls[1][3]).toEqual(api.action.mock.calls[0][3]);
    expect(api.action.mock.calls[1][3].expectedTaskRevision).toBe(4);
    second.unmount();
    sessionStorage.clear();
  });
  it('starts v2 with a stable request identity after an uncertain create and keeps legacy operations unused', async () => {
    const task = { id: 't', revision: 4, researchRuns: [] };
    const workspace = { tasks: [task], adoptServerTask: vi.fn() };
    const operations = { start: vi.fn() };
    const api = { start: vi.fn().mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce({
      workspace: { ...task, researchRuns: [{ researchId: 'r' }] },
      task: { taskId: 't', runId: 'r', contractVersion: 2, status: 'running', runRevision: 1 },
    }) };
    const { result, unmount } = renderHook(() => useTaskResearch(workspace, api, operations));
    const context = { engineVersion: 'deep-research-v2', allowedPaperIds: ['a', 'b'], primaryPaperId: 'a' };
    await act(async () => { await expect(result.current.start(task, '研究', context)).rejects.toThrow('网络中断'); });
    await act(async () => result.current.start(task, '研究', context));
    expect(operations.start).not.toHaveBeenCalled();
    const first = api.start.mock.calls[0][1];
    expect(api.start.mock.calls[1][1].requestId).toBe(first.requestId);
    expect(first.materialSelection).toEqual({ mode: 'explicit', materialIds: ['a', 'b'] });
    expect(first.sourcePolicy).toEqual({ mode: 'task_only' });
    expect(result.current.runs['t/r'].status).toBe('running');
    unmount();
  });
  it('adopts a bound continuation as a child without overwriting its parent state', async () => {
    const task = { id: 't', researchRuns: [{ researchId: 'parent' }] };
    const saved = { ...task, researchRuns: [...task.researchRuns, { researchId: 'child' }] };
    const workspace = { tasks: [task], adoptServerTask: vi.fn() };
    const api = { get: vi.fn(async () => ({ workspace: task, task: {
      taskId: 't', runId: 'parent', contractVersion: 2, status: 'completed', outcome: 'partial', runRevision: 8,
    } })), action: vi.fn(async () => ({ workspace: saved, task: {
      taskId: 't', runId: 'child', parentRunId: 'parent', contractVersion: 2, status: 'running', runRevision: 1,
    } })) };
    const { result, unmount } = renderHook(() => useTaskResearch(workspace, api));
    await waitFor(() => expect(result.current.runs['t/parent']?.status).toBe('completed'));
    await act(async () => result.current.action('t', 'parent', 'continue', { requestId: 'next', expectedRunRevision: 8 }));
    expect(result.current.runs['t/parent'].runRevision).toBe(8);
    expect(result.current.runs['t/child'].runRevision).toBe(1);
    expect(workspace.adoptServerTask).toHaveBeenLastCalledWith(saved);
    unmount();
  });
  it('rejects a continuation that points to an unbound child', async () => {
    const task = { id: 't', researchRuns: [{ researchId: 'parent' }] };
    const workspace = { tasks: [task], adoptServerTask: vi.fn() };
    const api = { get: vi.fn(async () => ({ task: { taskId: 'parent', status: 'running' } })),
      action: vi.fn(async () => ({ workspace: task, task: {
        taskId: 't', runId: 'foreign', parentRunId: 'parent', contractVersion: 2, status: 'running', runRevision: 1,
      } })) };
    const { result, unmount } = renderHook(() => useTaskResearch(workspace, api));
    await act(async () => { await expect(result.current.action('t', 'parent', 'continue', { expectedRunRevision: 1 })).rejects.toThrow('绑定未确认'); });
    expect(workspace.adoptServerTask).not.toHaveBeenCalled();
    unmount();
  });
  it('rejects a v2 run belonging to another product task', async () => {
    const task = { id: 't', researchRuns: [{ researchId: 'r' }] };
    const workspace = { tasks: [task], activeTaskId: 't', adoptServerTask: vi.fn() };
    const api = { get: vi.fn(async () => ({ task: { contractVersion: 2, runId: 'r', taskId: 'other', status: 'running', runRevision: 1 } })) };
    const { result, unmount } = renderHook(() => useTaskResearch(workspace, api));
    await waitFor(() => expect(result.current.error).toContain('任务不匹配'));
    expect(result.current.runs['t/r']).toBeUndefined();
    unmount();
  });
  it('does not adopt a v2 state older than a confirmed run revision', async () => {
    const task = { id: 't', researchRuns: [{ researchId: 'r' }] };
    const workspace = { tasks: [task], activeTaskId: 't', adoptServerTask: vi.fn() };
    let revision = 8;
    const api = { get: vi.fn(async () => ({ workspace: task, task: { contractVersion: 2, runId: 'r', taskId: 't', status: 'running', runRevision: revision } })) };
    const { result, unmount } = renderHook(() => useTaskResearch(workspace, api));
    await waitFor(() => expect(result.current.runs['t/r']?.runRevision).toBe(8));
    revision = 7;
    await act(async () => result.current.refresh('t', 'r'));
    expect(result.current.runs['t/r'].runRevision).toBe(8);
    expect(workspace.adoptServerTask).toHaveBeenCalledTimes(1);
    unmount();
  });
  it('keeps the newest confirmed action when two explicit action replies arrive out of order', async () => {
    const task={id:'t',researchRuns:[{researchId:'r'}]};
    const workspace={tasks:[task],activeTaskId:'t',adoptServerTask:vi.fn()};
    let releaseOlder;
    const api={get:vi.fn(async()=>({task:{taskId:'r',status:'running'}})),
      action:vi.fn().mockImplementationOnce(()=>new Promise(resolve=>{releaseOlder=resolve}))
        .mockResolvedValueOnce({workspace:task,task:{taskId:'r',status:'running'}})};
    const {result,unmount}=renderHook(()=>useTaskResearch(workspace,api));
    await act(async()=>{});
    let older;
    act(()=>{older=result.current.action('t','r','cancel',{})});
    await act(async()=>result.current.action('t','r','retry',{}));
    await act(async()=>{releaseOlder({workspace:task,task:{taskId:'r',status:'cancelled'}});await older});
    expect(result.current.runs['t/r'].status).toBe('running');
    expect(workspace.adoptServerTask).toHaveBeenCalledTimes(1);
    expect(api.action).toHaveBeenCalledTimes(2);
    unmount();
  });
  it('does not expose a response with the wrong workspace identity', async () => {
    const task={id:'t',researchRuns:[{researchId:'r'}]};
    const workspace={tasks:[task],activeTaskId:'t',adoptServerTask:vi.fn()};
    const api={get:vi.fn(async()=>({workspace:{id:'other'},task:{taskId:'r',status:'succeeded'}}))};
    const {result,unmount}=renderHook(()=>useTaskResearch(workspace,api));
    await waitFor(()=>expect(result.current.error).toContain('任务不匹配'));
    expect(result.current.runs['t/r']).toBeUndefined();
    expect(workspace.adoptServerTask).not.toHaveBeenCalled();
    unmount();
  });
  it('ignores an obsolete poll failure after a confirmed cancellation', async () => {
    const task={id:'t',researchRuns:[{researchId:'r'}]};
    const workspace={tasks:[task],activeTaskId:'t',adoptServerTask:vi.fn()};
    let rejectGet;
    const api={get:vi.fn(()=>new Promise((_,reject)=>{rejectGet=reject})),
      action:vi.fn(async()=>({workspace:task,task:{taskId:'r',status:'cancelled'}}))};
    const {result,unmount}=renderHook(()=>useTaskResearch(workspace,api));
    await act(async()=>result.current.action('t','r','cancel',{}));
    await act(async()=>rejectGet(new Error('旧请求超时')));
    expect(result.current.error).toBe('');
    expect(result.current.runs['t/r'].status).toBe('cancelled');
    unmount();
  });
  it('suspends GET for an action in flight while other research continues polling', async () => {
    vi.useFakeTimers();
    try {
      const task={id:'t',researchRuns:[{researchId:'r'},{researchId:'other'}]};
      const workspace={tasks:[task],activeTaskId:'t',adoptServerTask:vi.fn()};
      let releaseAction;
      const api={get:vi.fn(async(_,researchId)=>({task:{taskId:researchId,status:'running'}})),
        action:vi.fn(()=>new Promise(resolve=>{releaseAction=resolve}))};
      const {result,unmount}=renderHook(()=>useTaskResearch(workspace,api));
      await act(async()=>{});
      let actionPromise;
      act(()=>{actionPromise=result.current.action('t','r','cancel',{})});
      await act(async()=>vi.advanceTimersByTimeAsync(8000));
      expect(api.get.mock.calls.filter(([,id])=>id==='r')).toHaveLength(1);
      expect(api.get.mock.calls.filter(([,id])=>id==='other').length).toBeGreaterThan(1);
      await act(async()=>{releaseAction({workspace:task,task:{taskId:'r',status:'cancelled'}});await actionPromise});
      expect(result.current.runs['t/r'].status).toBe('cancelled');
      unmount();
    } finally {vi.useRealTimers()}
  });
  it('does not let a GET started before cancellation overwrite the confirmed cancellation', async () => {
    const task={id:'t',revision:1,researchRuns:[{researchId:'r'}]};
    const cancelledTask={...task,revision:2};
    const workspace={tasks:[task],activeTaskId:'t',adoptServerTask:vi.fn()};
    let releaseGet;
    const api={get:vi.fn(()=>new Promise(resolve=>{releaseGet=resolve})),
      action:vi.fn(async()=>({workspace:cancelledTask,task:{taskId:'r',status:'cancelled'}}))};
    const {result,unmount}=renderHook(()=>useTaskResearch(workspace,api));
    await act(async()=>result.current.action('t','r','cancel',{}));
    expect(result.current.runs['t/r'].status).toBe('cancelled');
    await act(async()=>releaseGet({workspace:task,task:{taskId:'r',status:'running'}}));
    expect(result.current.runs['t/r'].status).toBe('cancelled');
    expect(workspace.adoptServerTask).toHaveBeenCalledTimes(1);
    expect(workspace.adoptServerTask).toHaveBeenCalledWith(cancelledTask);
    unmount();
  });
  it.each(['cancelled', 'failed', 'succeeded'])('stops GET polling after confirmed %s even when another run is added', async status => {
    vi.useFakeTimers();
    try {
      const task = { id:'t', researchRuns:[{researchId:'done'}] };
      const workspace = { tasks:[task], activeTaskId:'t', adoptServerTask:vi.fn() };
      const api = { get:vi.fn(async (_taskId, researchId) => ({workspace:task,
        task:{taskId:researchId,status:researchId === 'done' ? status : 'running'}})) };
      const {rerender,unmount} = renderHook(({current}) => useTaskResearch(current,api), {initialProps:{current:workspace}});
      await act(async () => {});
      await act(async () => vi.advanceTimersByTimeAsync(12000));
      expect(api.get.mock.calls.filter(([,id])=>id==='done')).toHaveLength(1);
      rerender({current:{...workspace,tasks:[{...task,researchRuns:[...task.researchRuns,{researchId:'new'}]}]}});
      await act(async () => vi.advanceTimersByTimeAsync(4000));
      expect(api.get.mock.calls.filter(([,id])=>id==='done')).toHaveLength(1);
      expect(api.get.mock.calls.filter(([,id])=>id==='new').length).toBeGreaterThan(1);
      unmount();
    } finally { vi.useRealTimers(); }
  });
  it('resumes GET recovery after an explicit action with an uncertain response without repeating the action', async () => {
    vi.useFakeTimers();
    try {
      const task = {id:'t',researchRuns:[{researchId:'r'}]};
      const workspace = {tasks:[task],activeTaskId:'t',adoptServerTask:vi.fn()};
      let status='cancelled';
      const api = {get:vi.fn(async () => ({workspace:task,task:{taskId:'r',status}})),
        action:vi.fn(async () => {status='running';throw new Error('操作返回未确认');})};
      const {result,unmount} = renderHook(() => useTaskResearch(workspace,api));
      await act(async () => {});
      await act(async () => vi.advanceTimersByTimeAsync(4000));
      expect(api.get).toHaveBeenCalledTimes(1);
      await act(async () => result.current.action('t','r','retry',{}));
      await act(async () => vi.advanceTimersByTimeAsync(8000));
      expect(result.current.runs['t/r'].status).toBe('running');
      expect(api.get.mock.calls.length).toBeGreaterThan(1);
      expect(api.action).toHaveBeenCalledTimes(1);
      expect(result.current.error).toBe('操作返回未确认');
      unmount();
    } finally { vi.useRealTimers(); }
  });
  it('clears a recovered poll error and keeps other task failures out of the current task', async () => {
    vi.useFakeTimers();
    try {
      const a = { id:'a', researchRuns:[{ researchId:'ra' }] };
      const b = { id:'a/child', researchRuns:[{ researchId:'rb' }] };
      let recovered = false;
      const api = { get:vi.fn(async (taskId, researchId) => {
        if (taskId !== 'a' || !recovered) throw new Error(taskId + ':502');
        return { task:{ taskId:researchId, status:'awaiting_final_review' } };
      }) };
      const workspace = { tasks:[a,b], activeTaskId:'a', adoptServerTask:vi.fn() };
      const { result, rerender, unmount } = renderHook(({ current }) => useTaskResearch(current,api), { initialProps:{ current:workspace } });
      await act(async () => {});
      expect(result.current.error).toBe('a:502');
      recovered = true;
      await act(async () => vi.advanceTimersByTimeAsync(4000));
      expect(result.current.error).toBe('');
      rerender({ current:{ ...workspace, activeTaskId:b.id } });
      expect(result.current.error).toBe('a/child:502');
      unmount();
    } finally { vi.useRealTimers(); }
  });
  it('does not hide an unconfirmed action error merely because polling recovers', async () => {
    vi.useFakeTimers();
    try {
      const task = { id:'t', researchRuns:[{ researchId:'r' }] };
      const workspace = { tasks:[task], activeTaskId:'t' };
      const api = { get:vi.fn(async () => ({ task:{ taskId:'r', status:'awaiting_plan_review' } })),
        action:vi.fn(async () => { throw new Error('计划保存未确认'); }) };
      const { result, unmount } = renderHook(() => useTaskResearch(workspace,api));
      await act(async () => result.current.action('t','r','plan-review',{}));
      await act(async () => vi.advanceTimersByTimeAsync(4000));
      expect(result.current.error).toBe('计划保存未确认');
      unmount();
    } finally { vi.useRealTimers(); }
  });
  it('creates research with a material snapshot and external retrieval disabled', async () => {
    const task = { id: 't', revision: 4, focusedPaperId: 'a', researchRuns: [] };
    const workspace = { tasks: [task], adoptServerTask: vi.fn(), updateTask: vi.fn() };
    const api = { start: vi.fn(async () => ({ task, result: { task: { taskId: 'r', status: 'pending' } } })) };
    const { result } = renderHook(() => useTaskResearch(workspace, api));
    await act(async () => result.current.start(task, '研究方法', { allowedPaperIds: ['a', 'b'], primaryPaperId: null }));
    expect(api.start).toHaveBeenCalledWith('t', { question: '研究方法', pdfId: 'a', allowedPaperIds: ['a', 'b'], expectedTaskRevision: 4, allowExternalSearch: false, allowWebSearch: false });
    expect(workspace.adoptServerTask).toHaveBeenCalledWith(task);
  });
  it('restores a completed run into its original task without duplicating saved results', async () => {
    const task = { id: 'original', messages: [], artifacts: [], researchRuns: [{ researchId: 'r', question: '研究', paperIds: ['a'], primaryPaperId: 'a' }] };
    const workspace = { tasks: [task], activeTaskId: 'other', updateTask: vi.fn(), adoptServerTask: vi.fn() };
    const saved = { ...task, messages: [{ id: 'research:r:answer', content: '有证据的结果', artifactId: 'research:r:artifact' }],
      artifacts: [{ id: 'research:r:artifact', text: '## 结论\n有证据的结果' }] };
    const response = { workspace: saved, task: { taskId: 'r', status: 'succeeded', report: '## 结论\n有证据的结果', findings: [] } };
    const api = { get: vi.fn(async () => response), action: vi.fn(async () => response) };
    const { result } = renderHook(() => useTaskResearch(workspace, api));
    await waitFor(() => expect(workspace.adoptServerTask).toHaveBeenCalledWith(saved));
    expect(workspace.updateTask).not.toHaveBeenCalled();
    await act(async () => result.current.action('original', 'r', 'final-review', {}));
    expect(workspace.adoptServerTask).toHaveBeenLastCalledWith(saved);
    expect(workspace.updateTask).not.toHaveBeenCalled();
  });
  it('does not fabricate locally saved results when server publication is unconfirmed', async () => {
    const task = { id: 't', researchRuns: [{ researchId: 'r' }] };
    const workspace = { tasks: [task], updateTask: vi.fn(), adoptServerTask: vi.fn() };
    const api = { get: vi.fn(async () => ({ task: { taskId: 'r', status: 'succeeded', report: '完整报告' } })) };
    const { result } = renderHook(() => useTaskResearch(workspace, api));
    await waitFor(() => expect(result.current.error).toContain('保存尚未确认'));
    expect(workspace.updateTask).not.toHaveBeenCalled();
    expect(workspace.adoptServerTask).not.toHaveBeenCalled();
    expect(result.current.runs['t/r']).toBeUndefined();
  });
});
