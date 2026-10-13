import React, { useRef, useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink, FileText, Plus, X } from 'lucide-react';

const labels = {
  queued: '研究已排队', running: '正在研究', waiting_user: '需要明确研究范围',
  paused: '研究已暂停', stopping: '正在停止', cancelled: '研究已停止', failed: '本次研究未完成',
};
const outcomes = { complete: '报告已保存', partial: '已完成部分研究', inconclusive: '当前材料不足以判断', none: '研究已结束' };
const actionLabels = { pause: '暂停', resume: '继续研究', cancel: '停止', continue: '补查缺口' };
const accessLabels = { fulltext: '全文片段', full_text: '全文片段', abstract: '仅摘要', metadata: '仅元数据' };

/** Version 2 execution details are optional; the answer remains the primary content. */
export default function ResearchResultCard({ taskId, run, result, error, onAction, onRefresh, onOpenReport, onJumpToSource, onAddSource }) {
  const [details, setDetails] = useState(false);
  const [tab, setTab] = useState('plan');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const [clarification, setClarification] = useState('');
  const [planDraft, setPlanDraft] = useState(null);
  const [addSourceBusy, setAddSourceBusy] = useState('');
  const [addedSources, setAddedSources] = useState(new Set());
  const [followup, setFollowup] = useState(false);
  const [followupQuestion, setFollowupQuestion] = useState('');
  const [useCurrentMaterials, setUseCurrentMaterials] = useState(false);
  const button = useRef(null);
  const requests = useRef(new Map());
  const actions = new Set(Array.isArray(result.allowedActions) ? result.allowedActions : []);
  const terminal = ['completed', 'cancelled', 'failed'].includes(result.status);
  const report = Boolean(result.reportVersionId || result.report?.versionId || (typeof result.report === 'string' && result.report.trim()));
  const rawTitle = result.title || result.brief?.title || '学术研究';
  const title = rawTitle.length > 48 ? ({ paper_comparison: '论文比较', claim_verification: '主张核查',
    experiment_design: '实验方案', direction_survey: '方向调研', research_entry: '研究切入点' }[result.outputKind || run.outputKind] || '学术研究') : rawTitle;
  const status = result.status === 'completed' ? outcomes[result.outcome] || '研究已完成' : labels[result.status] || '正在确认研究状态';
  const activity = typeof result.activity === 'string' ? result.activity : result.activity?.label;
  const rawError = failure || error?.action || error?.poll || result.error;
  const shownError = typeof rawError === 'string' ? rawError : rawError?.message || '';
  const close = () => { setDetails(false); button.current?.focus(); };
  const act = async (name, payload = {}) => {
    if (busy || !onAction || !actions.has(name)) return;
    const revision = result.runRevision ?? result.revision;
    const key = JSON.stringify([name, revision, payload]);
    if (!requests.current.has(key)) requests.current.set(key, globalThis.crypto?.randomUUID?.() || `research-${Date.now()}-${Math.random().toString(36).slice(2)}`);
    setBusy(true); setFailure('');
    try {
      await onAction(taskId, run.researchId, name, { ...payload, expectedRunRevision: revision, requestId: requests.current.get(key) });
    } catch (cause) { setFailure(cause?.message || '操作结果暂未确认，请查询状态。'); }
    finally { setBusy(false); }
  };
  const sources = Array.isArray(result.sources) ? result.sources : [];
  const planItems = Array.isArray(result.plan) ? result.plan : Array.isArray(result.plan?.items) ? result.plan.items : [];
  const planRevision = result.plan?.revision ?? result.planRevision;
  const events = Array.isArray(result.events) ? result.events : [];
  const canEditPlan = result.status === 'paused' && actions.has('plan') && planItems.length > 0;
  const handlePlanSave = () => {
    if (!canEditPlan) return;
    const items = (planDraft || planItems).map((item, index) => ({
      ...item,
      itemId: item.itemId || `plan-${index}`,
      question: item.question || '',
      obligations: item.obligations || [],
    })).filter(item => item.question.trim());
    if (!items.length) return;
    void act('plan', { plan: items, planRevision });
  };
  const handleAddSource = async (source) => {
    if (!onAddSource || addSourceBusy) return;
    const sourceId = source.sourceId || source.workId;
    if (!sourceId) return;
    setAddSourceBusy(sourceId);
    try {
      await onAddSource(taskId, run.researchId, sourceId);
      setAddedSources(current => new Set([...current, sourceId]));
    } catch (cause) { setFailure(cause?.message || '加入任务材料未完成，请重试。'); }
    finally { setAddSourceBusy(''); }
  };
  return <article className="conversation-research-card research-result-card" aria-label="研究结果">
    <div className="research-result-heading"><strong>{title}</strong><span role="status" aria-live="polite">{status}</span></div>
    {!terminal && activity && <p className="theme-text-muted text-sm">{activity}</p>}
    {result.summary && <p className="research-result-summary">{result.summary}</p>}
    {result.status === 'waiting_user' && <form onSubmit={event => { event.preventDefault(); void act('clarify', { answer: clarification.trim() }); }}>
      <label>{result.clarification?.question || '请明确本次研究目标'}
        <input aria-label="研究范围答复" className="theme-input" value={clarification} onChange={event => setClarification(event.target.value)} />
      </label>
      {(result.clarification?.options || []).map(option => <button type="button" disabled={busy || !actions.has('clarify')} key={option}
        onClick={() => act('clarify', { answer: option })}>{option}</button>)}
      <button type="submit" disabled={busy || !clarification.trim() || !actions.has('clarify')}>继续</button>
    </form>}
    <div className="research-result-actions">
      {report && onOpenReport && <button type="button" onClick={() => onOpenReport(run, result)}><FileText size={14} />{result.outcome === 'partial' ? '查看已有结果' : '打开报告'}</button>}
      {['cancel', 'resume', 'continue', 'pause'].filter(action => actions.has(action)).map(action =>
        <button type="button" key={action} disabled={busy || !onAction} onClick={() => action === 'continue' ? setFollowup(value => !value) : act(action)}>{actionLabels[action]}</button>)}
      <button type="button" ref={button} aria-expanded={details} onClick={() => setDetails(value => !value)}>
        {details ? <ChevronUp size={14} /> : <ChevronDown size={14} />}{terminal ? `来源与详情${result.sourceCount ? ` (${result.sourceCount})` : ''}` : '详情'}
      </button>
    </div>
    {followup && actions.has('continue') && <form className="research-followup" onSubmit={event => {
      event.preventDefault(); void act('continue', { question: followupQuestion.trim() || run.question || result.title,
        ...(useCurrentMaterials ? { materialSelection: { mode: 'task_default' } } : {}) });
    }}>
      <label>继续研究什么？<textarea className="theme-input" value={followupQuestion} onChange={event => setFollowupQuestion(event.target.value)}
        placeholder="例如：补找反对证据；留空则继续补查原问题" /></label>
      <label><input type="checkbox" checked={useCurrentMaterials} onChange={event => setUseCurrentMaterials(event.target.checked)} />使用当前任务材料（含新加入的论文）</label>
      <p className="theme-text-muted text-sm">复用仍有效的证据；新的查询和生成会使用一次标准研究预算。</p>
      <button type="submit" disabled={busy}>开始补查</button><button type="button" onClick={() => setFollowup(false)}>取消</button>
    </form>}
    {shownError && <div><p role="alert">{shownError}</p>{onRefresh && <button type="button" disabled={busy} onClick={() => onRefresh(taskId, run.researchId)}>查询状态</button>}</div>}
    {details && <section className="research-result-details" aria-label="研究详情" onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); close(); } }}>
      <div className="research-result-details-heading"><strong>研究详情</strong><button type="button" aria-label="关闭研究详情" onClick={close}><X size={14} /></button></div>
      <div role="tablist" aria-label="研究详情分类">{[['plan', '计划'], ['sources', '资料'], ['events', '执行记录']].map(([id, label]) =>
        <button type="button" role="tab" aria-selected={tab === id} key={id} onClick={() => setTab(id)}>{label}</button>)}</div>
      <div role="tabpanel" aria-label={{ plan: '计划', sources: '资料', events: '执行记录' }[tab]}>
        {tab === 'plan' && <>
          {canEditPlan && <div className="research-plan-editor">
            <p className="theme-text-muted text-sm">研究已暂停，可调整计划后继续。</p>
            <ol>{(planDraft || planItems).map((item, index) => <li key={item.itemId || index}>
              <label>
                <input className="theme-input" value={(planDraft || planItems)[index]?.question || ''}
                  onChange={event => {
                    const draft = [...(planDraft || planItems)];
                    const question = event.target.value;
                    const previous = draft[index];
                    // A one-obligation item edits its actual executable question too.
                    draft[index] = { ...previous, question, searchQuery: undefined, obligations: previous.obligations?.length === 1
                      ? previous.obligations.map(obligation => ({ ...obligation, question, searchQuery: undefined })) : previous.obligations };
                    setPlanDraft(draft);
                  }} />
              </label>
              {(item.obligations || []).length > 1 && item.obligations.map((obligation, obligationIndex) => <label key={obligation.obligationId}>
                核对问题 {obligationIndex + 1}
                <input className="theme-input" aria-label={`核对问题 ${obligationIndex + 1}`} value={(planDraft || planItems)[index].obligations[obligationIndex].question || ''}
                  onChange={event => {
                    const draft = [...(planDraft || planItems)];
                    draft[index] = { ...draft[index], obligations: draft[index].obligations.map((value, at) => at === obligationIndex ? { ...value, question: event.target.value, searchQuery: undefined } : value) };
                    setPlanDraft(draft);
                  }} />
              </label>)}
              <span className="theme-text-muted"> {({ completed: '已完成', pending: '待研究', running: '研究中', gap: '待补查' })[item.status] || ''}</span>
            </li>)}</ol>
            <button type="button" disabled={busy || !actions.has('plan')} onClick={handlePlanSave}>提交修改</button>
          </div>}
          {!canEditPlan && (planItems.length ? <ol>{planItems.map((item, index) => <li key={item.itemId || index}>{typeof item === 'string' ? item : item.question}<span className="theme-text-muted"> {({ completed: '已完成', pending: '待研究', running: '研究中', gap: '待补查' })[item.status] || ''}</span></li>)}</ol> : <p>暂未生成计划。</p>)}
        </>}
        {tab === 'sources' && (sources.length ? <ul className="research-source-list">{sources.map((source, index) => {
          const sourceId = source.sourceId || source.workId || `source-${index}`;
          const isExternal = ['external', 'arxiv'].includes(source.sourceKind) || source.external === true;
          const addedToTask = source.addedToTask === true || addedSources.has(sourceId);
          const adding = addSourceBusy === sourceId;
          return <li key={sourceId} className="research-source-item">
            <div className="research-source-header">
              <strong>{source.title || source.pdfId || '论文来源'}</strong>
              <span className="research-source-access">{accessLabels[source.accessLevel] || (isExternal ? '外部来源' : '任务材料')}</span>
            </div>
            {source.page != null && <span className="research-source-location">第 {source.page} 页{source.section ? ` · ${source.section}` : ''}</span>}
            {source.quote && <details className="research-source-quote"><summary>原文依据</summary><blockquote>{source.quote}</blockquote></details>}
            <div className="research-source-actions">
              {onJumpToSource && source.pdfId && !isExternal && <button type="button" onClick={() => onJumpToSource({ ...source, pageIndex: source.page != null ? source.page - 1 : source.pageIndex })}>查看论文原文</button>}
              {isExternal && source.url && <a href={source.url} target="_blank" rel="noopener noreferrer" className="research-source-external-link"><ExternalLink size={12} />来源页面</a>}
              {isExternal && onAddSource && !addedToTask && <button type="button" disabled={adding} onClick={() => handleAddSource(source)}>
                {adding ? '加入中…' : <><Plus size={12} />加入任务材料</>}
              </button>}
              {isExternal && addedToTask && <span className="research-source-added" role="status">已加入任务</span>}
              {isExternal && !source.url && source.accessLevel === 'abstract' && <span className="theme-text-muted text-sm">仅获取摘要</span>}
            </div>
          </li>;
        })}</ul> : <p>{result.sourceCount ? '来源详情可在报告中展开。' : '尚无可引用来源。'}</p>)}
        {tab === 'events' && (events.length ? <ol className="research-event-list">{events.map((event, index) => <li key={event.eventId || event.callId || index}>
          <span className="research-event-label">{event.label || event.activity || event.kind || event.toolName || '步骤'}</span>
          {event.summary && <span className="research-event-summary">：{event.summary}</span>}
          {event.status && event.status !== 'completed' && <span className="theme-text-muted"> ({event.status})</span>}
        </li>)}</ol> : <p>尚无执行记录。</p>)}
      </div>
    </section>}
  </article>;
}
