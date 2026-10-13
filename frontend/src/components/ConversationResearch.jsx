import React, { useState } from 'react';
import { getResearchStatusMeta } from './deepResearchPanelModel';
import { researchTitle } from './conversationProcessingModel';
import ResearchResultCard from './ResearchResultCard';

export function ResearchCard({ taskId, run, result, error, onRefresh, onAction, onOpenReport, onJumpToSource, onAddSource, compactTitle, inline = true }) {
  const [actionError, setActionError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reviews, setReviews] = useState({});
  const draftKey = `pixiu-research-plan:${JSON.stringify([taskId, run.researchId])}`;
  const [planDraft, setPlanDraft] = useState(() => { try { return localStorage.getItem(draftKey); } catch { return null; } });
  const act = async (action, payload) => {
    if (busy || !onAction) return;
    setBusy(true); setActionError('');
    try { await onAction(taskId, run.researchId, action, payload); }
    catch (error) { setActionError(error?.message || '操作未完成，请重试。'); }
    finally { setBusy(false); }
  };
  const title = researchTitle(run, result, compactTitle);
  if (result?.contractVersion === 2) return <ResearchResultCard {...{ taskId, run, result, error, onRefresh, onAction, onOpenReport, onJumpToSource, onAddSource }} />;
  const failure = actionError || error?.action || error?.poll;
  const errorDetail = failure && <details><summary>研究状态需确认</summary><p role="alert">{failure}</p>
    {onRefresh && <button type="button" disabled={busy} onClick={() => onRefresh(taskId, run.researchId)}>查询研究状态</button>}</details>;
  if (!result) return <article className="conversation-research-card"><span role="status">{failure ? '暂时无法读取研究' : '正在读取研究'}：{title}</span>{errorDetail}</article>;
  if (result.status === 'succeeded') return <article className="conversation-research-card">
    <strong>{title}</strong> · <span>已保存</span>
    <button type="button" disabled={!onOpenReport} onClick={() => onOpenReport?.(run, result)}>打开研究报告</button>
  </article>;
  const plan = (result.plan || []).map((item) => typeof item === 'string' ? item : item.question || item.subQuestion || '').filter(Boolean);
  const risks = result.reviewRisks || [];
  return <article className="conversation-research-card">
    <div><strong>{inline ? title : run.question || title}</strong> · <span>{getResearchStatusMeta(result.status).label}</span></div>
    {result.status === 'awaiting_plan_review' && <>
      <label>研究问题<textarea aria-label="研究问题列表" value={planDraft ?? plan.join('\n')} onChange={(event) => {
        setPlanDraft(event.target.value); try { localStorage.setItem(draftKey, event.target.value); } catch { /* Keep the editable draft in memory. */ }
      }} /></label>
      <button type="button" disabled={busy || !onAction || !(planDraft ?? plan.join('\n')).trim()} onClick={() => act('plan-review', { subQuestions: (planDraft ?? plan.join('\n')).split('\n').map((line) => line.trim()).filter(Boolean), reviewNotes: '' })}>按这些问题研究</button>
    </>}
    {result.status === 'awaiting_final_review' && <>
      <p>报告已生成，核对后可保存为成果。</p>
      <button type="button" disabled={!onOpenReport} onClick={() => onOpenReport?.(run, result)}>打开研究报告</button>
      {risks.map((risk) => <label key={risk.riskId} className="research-risk">{risk.label}：{risk.detail}
        <select aria-label={`核对：${risk.detail}`} value={reviews[risk.riskId] || ''} onChange={(event) => setReviews((value) => ({ ...value, [risk.riskId]: event.target.value }))}>
          <option value="">选择核对结果</option><option value="reviewed">已核对</option><option value="needs_follow_up">仍需后续研究</option>
        </select>
      </label>)}
      <button type="button" disabled={busy || !onAction || risks.some((risk) => !reviews[risk.riskId])} onClick={() => act('final-review', { reviewNotes: '', riskReviews: risks.map((risk) => ({ riskId: risk.riskId, reviewStatus: reviews[risk.riskId] })) })}>确认并保存结果</button>
    </>}

    {errorDetail}
    {result.error && <p role="alert">{result.error}</p>}
    {['failed', 'cancelled'].includes(result.status) && result.plan?.length > 0 && <button type="button" disabled={busy || !onAction} onClick={() => act('resume')}>继续未完成的研究</button>}
    {!['succeeded', 'failed', 'cancelled'].includes(result.status) && <button type="button" disabled={busy || !onAction} onClick={() => act('cancel')}>取消研究</button>}
  </article>;
}
export default function ConversationResearch({ task, research, onJumpToSource, onOpenReport }) {
  return <div className="conversation-research-list">{(task.researchRuns || []).map((run) => <ResearchCard key={run.researchId} taskId={task.id} run={run}
    result={research.runs[`${task.id}/${run.researchId}`]} onAction={research.action} onJumpToSource={onJumpToSource} onOpenReport={onOpenReport} />)}</div>;
}
