import React, { useEffect, useRef, useState } from 'react';
import MarkdownContent from './MarkdownContent';
import ResearchReportText from './ResearchReportText';
import { SourceChip } from './SourceCitation';
import { normalizeEvidenceSources } from './evidenceCitationModel';
import { paperShortName } from '../utils/documentPresentation';
/** @type {Array<{ id: string, title?: string, filename?: string }>} */
const EMPTY_PAPERS = [];

export const hasGroupedCritique = value => value?.critique?.schemaVersion === 2;
const readableCitationSpacing = text => typeof text === 'string' ? text.replace(/([。！？.!?）)])\s+(\[\d+\])/gu, '$1\u00a0$2') : text;

function linkedSources(value, linked, papers) {
  const lookup = new Map((value.sources || value.rag_sources || []).map(source => [source.sourceId || source.id, source]));
  const references = linked.flatMap(claim => (claim.references || []).flatMap(reference => {
    const sourceId = typeof reference === 'string' ? reference : reference.sourceId;
    const source = lookup.get(sourceId);
    return source ? [{ ...source, text: reference.quote || source.text, literalQuote: reference.quote,
      paperTitle: source.paperTitle || source.metadata?.paperTitle || papers.find(paper => paper.id === (source.pdfId || source.metadata?.pdfId))?.title
        || papers.find(paper => paper.id === (source.pdfId || source.metadata?.pdfId))?.filename }] : [];
  }));
  return [...new Map(references.map(source => [JSON.stringify([source.sourceId || source.id, source.text]), source])).values()];
}

// Only explicit server identities establish relationships. Legacy prose is never parsed.
export function critiqueIssues(value, target = 'chat', papers = []) {
  if (!hasGroupedCritique(value)) return [];
  const critique = value.critique;
  const claims = new Map((critique.claims || []).map(claim => [claim.id, claim]));
  const issues = new Map((critique.issues || []).map(issue => [issue.id, issue]));
  const blocks = new Map((critique[target === 'chat' ? 'chatBlocks' : 'artifactBlocks'] || []).map(block => [block.issueId, block.text]));
  return (critique.presentation?.[target === 'chat' ? 'chatIssueIds' : 'artifactIssueIds'] || []).flatMap(id => {
    const issue = issues.get(id);
    if (!issue) return [];
    const linked = [issue.conclusionClaimId, ...(issue.supportClaimIds || []), issue.implicationClaimId]
      .filter(Boolean).map(claimId => claims.get(claimId)).filter(Boolean);
    return [{ ...issue, text: blocks.get(id),
      sources: linkedSources(value, linked, papers), pending: (critique.pending || []).filter(item => issue.relatedPendingIds?.includes(item.id)) }];
  });
}

export default function CritiqueContent({ value, text, target = 'chat', papers = EMPTY_PAPERS, storageKey = '', onJumpToSource, onFollowup, className = '' }) {
  const grouped = hasGroupedCritique(value);
  const issues = critiqueIssues(value, target, papers);
  // Edited text remains authoritative for the document view; old claim text must not overwrite it.
  const standalone = value.capability === 'critique' || value.critique?.presentation?.standalone === true;
  const structured = standalone && grouped && !value.edited && issues.length > 0 && issues.every(issue => issue.text);
  const lead = target === 'artifact' ? value.critique?.artifactLead ?? value.critique?.lead : value.critique?.lead;
  const leadClaims = (value.critique?.claims || []).filter(claim => value.critique?.presentation?.leadClaimIds?.includes(claim.id));
  const leadIssue = { id: 'lead', text: lead, sources: linkedSources(value, leadClaims, papers), pending: [] };
  const visiblePending = target === 'artifact' ? value.critique?.artifactPending ?? value.critique?.visiblePending : value.critique?.visiblePending;
  const linkedPending = new Set(issues.flatMap(issue => issue.relatedPendingIds || []));
  const pending = (value.critique?.pending || []).filter(item => !linkedPending.has(item.id));
  return <div className={className}>
    {value.edited && grouped && <p className="theme-text-muted text-xs">此版本含用户编辑；修改内容不作为论文原文依据。</p>}
    {structured ? <>
      {typeof lead === 'string' && lead && <CitedSection issue={leadIssue} value={value} storageKey={storageKey} lead onJumpToSource={onJumpToSource} />}
      {issues.map(issue => <CitedSection key={issue.id} issue={issue} value={value} storageKey={storageKey} onJumpToSource={onJumpToSource} onFollowup={onFollowup} />)}
    </> : <>
      {value.sourceRunId && value.edited && <p className="theme-text-muted text-sm">我的修改稿 · 修改内容尚未重新核验，原引用保留供参考。</p>}
      {value.sourceRunId || text?.includes('#research-evidence-') ? <ResearchReportText text={text} sources={value.sources || value.rag_sources || []} onJumpToSource={onJumpToSource} /> : <MarkdownContent>{text}</MarkdownContent>}
      {grouped && !value.edited && issues.map((issue, index) => <section key={issue.id} data-critique-issue-id={issue.id}>
        <IssueActions issue={issue} storageKey={storageKey} label={`第 ${index + 1} 点`} onJumpToSource={onJumpToSource} onFollowup={onFollowup} />
      </section>)}
    </>}
    {structured && visiblePending && <MarkdownContent>{visiblePending}</MarkdownContent>}
    {target === 'artifact' && grouped && !value.edited && pending.length > 0 && <details><summary>待核查</summary>
      {pending.map(item => <p key={item.id}>{item.whatToCheck || item.topic}</p>)}
    </details>}
  </div>;
}

function CitedSection({ issue, value, storageKey, lead = false, onJumpToSource, onFollowup }) {
  const [requested, setRequested] = useState(0);
  const [shown, setShown] = useState(() => { try { return !lead || (storageKey && localStorage.getItem(`${storageKey}:issue:${issue.id}`) === 'open'); } catch { return !lead; } });
  const sources = value.sources || value.rag_sources || [];
  const renderText = children => React.Children.map(children, child => {
    if (typeof child === 'string') return child.split(/(\[\d+\])/gu).map((part, index) => {
      const match = part.match(/^\[(\d+)\]$/u);
      const source = match && sources[Number(match[1]) - 1];
      const linked = source && issue.sources.some(item => (item.sourceId || item.id) === (source.sourceId || source.id));
      return linked ? <button type="button" key={index} className="critique-inline-citation" aria-label={`查看引用 ${match[1]} 的依据`} onClick={() => { setShown(true); setRequested(count => count + 1); }}>{part}</button> : part;
    });
    if (React.isValidElement(child) && !['code', 'a'].includes(child.type) && !String(child.props.className || '').includes('katex')) {
      return React.cloneElement(child, undefined, renderText(child.props.children));
    }
    return child;
  });
  return <section data-critique-issue-id={lead ? undefined : issue.id}>
    <MarkdownContent components={{ p: ({ children }) => <p>{renderText(children)}</p> }}>{readableCitationSpacing(issue.text)}</MarkdownContent>
    {issue.pending.map(item => <p key={item.id}>待核查：{item.whatToCheck || item.topic}</p>)}
    {shown && <IssueActions issue={issue} label={lead ? '总判断' : ''} storageKey={storageKey} openRequested={requested} onJumpToSource={onJumpToSource} onFollowup={onFollowup} />}
  </section>;
}

function IssueActions({ issue, storageKey, openRequested = 0, label = '', onJumpToSource, onFollowup }) {
  const key = storageKey ? `${storageKey}:issue:${issue.id}` : null;
  const detailsRef = useRef(null);
  const [expanded, setExpanded] = useState(() => { try { return key ? localStorage.getItem(key) === 'open' : false; } catch { return false; } });
  useEffect(() => {
    if (!openRequested || !detailsRef.current) return;
    detailsRef.current.open = true;
    detailsRef.current.querySelector('summary')?.focus();
    detailsRef.current.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
  }, [openRequested]);
  return <div className="reader-chat-citations critique-issue-actions">
    {issue.sources.length > 0 && <details ref={detailsRef} open={key ? expanded : undefined} onToggle={event => { if (key) { const open = event.currentTarget.open; setExpanded(open); try { localStorage.setItem(key, open ? 'open' : 'closed'); } catch { /* Reading state is optional. */ } } }}><summary className="reader-chat-citation">{label} 查看依据 · {issue.sources.length} 处</summary>
      {issue.sources.flatMap(source => normalizeEvidenceSources([source])).map((source, index) => <div key={`${source.sourceId}:${index}`} className="theme-card-soft rounded-lg p-3 text-xs leading-5">
        {(issue.sources[index]?.paperTitle || source.pdfId) && <p className="theme-text-muted text-xs" title={issue.sources[index]?.paperTitle}>{paperShortName({ title: issue.sources[index]?.paperTitle }, '任务论文')}{!issue.sources[index]?.literalQuote && source.locationLabel && ` · 索引 ${source.locationLabel}`}</p>}
        <MarkdownContent>{source.text}</MarkdownContent>
        <SourceChip source={{ ...source, literalQuote: issue.sources[index]?.literalQuote,
          ...(issue.sources[index]?.literalQuote ? { canJumpToSource: true, locationLabel: '· 按摘录定位' } : {}) }} onJumpToSource={onJumpToSource} />
      </div>)}
    </details>}
    {onFollowup && <button type="button" className="reader-chat-citation" onClick={() => onFollowup(issue.id)}>{label} 追问这一点</button>}
  </div>;
}
