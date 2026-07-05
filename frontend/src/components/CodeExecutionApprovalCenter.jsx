import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Code2, RefreshCw, Upload, X } from 'lucide-react';

import { apiService } from '../services/api.js';
import {
  canReviewExecution, canReviewPublication, groupCodeExecutionJobs, shortDigest,
} from './codeExecutionApprovalModel.js';

const errorMessage = (error) => error?.response?.data?.message || error?.message || '请求失败';

const CodeExecutionApprovalCenter = () => {
  const [open, setOpen] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      setError('');
      const response = await apiService.listCodeExecutionJobs();
      setJobs(response?.jobs || []);
      setSelectedId((current) => current || response?.jobs?.[0]?.jobId || '');
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }, []);

  useEffect(() => { if (open) refresh(); }, [open, refresh]);
  const selected = useMemo(() => jobs.find((job) => job.jobId === selectedId) || jobs[0] || null, [jobs, selectedId]);
  const groups = useMemo(() => groupCodeExecutionJobs(jobs), [jobs]);

  const upload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const staged = await apiService.uploadCodeExecutionArtifact(file);
      const created = await apiService.createCodeExecutionJob(staged.artifact.artifactId);
      setSelectedId(created.job.jobId);
      await refresh();
    } catch (requestError) { setError(errorMessage(requestError)); }
    finally { setBusy(false); event.target.value = ''; }
  };

  const review = async (kind, decision) => {
    if (!selected || busy) return;
    const reason = decision === 'rejected' ? window.prompt('可选：填写拒绝理由（最多 500 字）', '') || undefined : undefined;
    setBusy(true);
    setError('');
    try {
      const response = kind === 'execution'
        ? await apiService.reviewCodeExecution(selected.jobId, decision, selected.taskDigest, reason)
        : await apiService.reviewCodePublication(selected.jobId, decision, selected.publicationDigest, reason);
      setJobs((current) => current.map((job) => job.jobId === response.job.jobId ? response.job : job));
    } catch (requestError) {
      setError(errorMessage(requestError));
      await refresh();
    } finally { setBusy(false); }
  };

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="fixed bottom-5 right-5 z-[70] flex items-center gap-2 rounded-full bg-pixiu px-4 py-3 text-sm font-bold text-white shadow-xl">
        <Code2 size={18} /> 执行审批
      </button>
      {open && <div className="fixed inset-0 z-[90] flex bg-slate-950/50 backdrop-blur-sm">
        <div className="theme-panel ml-auto flex h-full w-full max-w-5xl flex-col shadow-2xl">
          <header className="theme-border flex items-center justify-between border-b p-4">
            <div><h2 className="theme-text-primary font-bold">代码执行审批中心</h2><p className="theme-text-muted text-xs">固定 CSV 描述统计 · 无网络 · 双重人工审批</p></div>
            <div className="flex gap-2">
              <label className="theme-button-secondary flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-xs"><Upload size={14} />上传 CSV<input type="file" accept=".csv,text/csv" className="hidden" disabled={busy} onChange={upload} /></label>
              <button type="button" onClick={refresh} className="theme-icon-button p-2" title="刷新"><RefreshCw size={16} /></button>
              <button type="button" onClick={() => setOpen(false)} className="theme-icon-button p-2" title="关闭"><X size={16} /></button>
            </div>
          </header>
          {error && <div className="m-3 rounded-md bg-red-500/10 px-3 py-2 text-xs text-red-500">{error}</div>}
          <div className="grid min-h-0 flex-1 grid-cols-[260px_1fr]">
            <aside className="theme-border overflow-y-auto border-r p-3">
              {groups.map((group) => <section key={group.key} className="mb-4"><h3 className="theme-text-muted mb-2 text-[11px] font-bold">{group.label} · {group.jobs.length}</h3>{group.jobs.map((job) => <button type="button" key={job.jobId} onClick={() => setSelectedId(job.jobId)} className={`mb-2 w-full rounded-md p-3 text-left text-xs ${selected?.jobId === job.jobId ? 'bg-pixiu/15 text-pixiu' : 'theme-card-soft'}`}><strong className="block truncate">{job.jobId}</strong><span>{job.status}</span></button>)}</section>)}
            </aside>
            <main className="overflow-y-auto p-5 text-sm">
              {!selected ? <p className="theme-text-muted">上传 CSV 创建固定分析任务。</p> : <div className="space-y-4">
                <section className="theme-card-soft rounded-lg p-4"><h3 className="theme-text-primary mb-2 font-bold">执行描述</h3><div className="grid gap-2 md:grid-cols-2"><span>输入：{selected.inputArtifacts?.[0]?.artifactId}</span><span>大小：{selected.inputArtifacts?.[0]?.sizeBytes} bytes</span><span>运行时：{selected.runtime?.name} {selected.runtime?.version}</span><span>模板：{selected.runtime?.templateId}</span><span>网络：{selected.networkPolicy}</span><span>镜像：{shortDigest(selected.image)}</span><span>任务摘要：{shortDigest(selected.taskDigest)}</span><span>脚本摘要：{shortDigest(selected.scriptDigest)}</span></div><pre className="mt-3 max-h-52 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">{selected.scriptText}</pre></section>
                <section className="theme-card-soft rounded-lg p-4"><h3 className="theme-text-primary mb-2 font-bold">资源限制与预期输出</h3><pre className="overflow-auto text-xs">{JSON.stringify({ limits: selected.limits, expectedOutputs: selected.expectedOutputs, dependencies: ['Python standard library'] }, null, 2)}</pre></section>
                {selected.executionResult && <section className="theme-card-soft rounded-lg p-4"><h3 className="theme-text-primary mb-2 font-bold">执行结果与审计</h3><p>状态：{selected.executionResult.status} / {selected.executionResult.reasonCode}</p><p>发布摘要：{shortDigest(selected.publicationDigest)}</p><pre className="mt-2 overflow-auto text-xs">{JSON.stringify({ outputs: selected.executionResult.outputs, warnings: selected.auditSummary?.warnings, auditEvents: selected.auditEvents }, null, 2)}</pre></section>}
                <div className="flex gap-2">
                  {canReviewExecution(selected) && <><button disabled={busy} onClick={() => review('execution', 'approved')} className="rounded-md bg-pixiu px-4 py-2 font-bold text-white">批准并执行</button><button disabled={busy} onClick={() => review('execution', 'rejected')} className="theme-button-secondary rounded-md px-4 py-2">拒绝执行</button></>}
                  {canReviewPublication(selected) && <><button disabled={busy} onClick={() => review('publication', 'approved')} className="rounded-md bg-emerald-600 px-4 py-2 font-bold text-white">批准发布</button><button disabled={busy} onClick={() => review('publication', 'rejected')} className="theme-button-secondary rounded-md px-4 py-2">拒绝发布</button></>}
                  {selected.publishable && <span className="rounded-full bg-emerald-500/10 px-3 py-2 text-xs font-bold text-emerald-500">已批准发布</span>}
                </div>
              </div>}
            </main>
          </div>
        </div>
      </div>}
    </>
  );
};

export default CodeExecutionApprovalCenter;
