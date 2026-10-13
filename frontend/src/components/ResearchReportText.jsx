import React, { useEffect, useMemo, useRef, useState } from 'react';
import MarkdownContent from './MarkdownContent';

/** Citation IDs come from the saved report, never from the currently open paper. */
export default function ResearchReportText({ text, sources = [], onJumpToSource }) {
  const [selected, setSelected] = useState(null);
  const trigger = useRef(null);
  const preview = useRef(null);
  const close = () => { setSelected(null); trigger.current?.focus(); };
  useEffect(() => { if (selected) preview.current?.focus(); }, [selected]);
  const components = useMemo(() => ({ a: ({ href, children }) => {
    if (!href?.startsWith('#research-evidence-')) return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    const evidenceId = href.slice('#research-evidence-'.length);
    const source = sources.find(value => value.evidenceIds?.includes(evidenceId) || value.evidenceId === evidenceId);
    const exact = source?.evidenceQuotes?.[evidenceId];
    const resolved = exact?.quote ? { ...source, evidenceId, quote: exact.quote, location: exact.location,
      page: exact.location ? exact.location.page : source.page,
      pageIndex: exact.location ? exact.location.pageIndex : source.pageIndex } : source && (source.evidenceId === evidenceId || source.evidenceIds?.length === 1)
      ? source : { unavailable: true };
    return <button type="button" className="critique-inline-citation" aria-label={`查看引用 ${children} 的依据`}
      onClick={event => { trigger.current = event.currentTarget; setSelected(resolved); }}>{children}</button>;
  } }), [sources]);
  const external = selected?.sourceKind === 'arxiv' || selected?.sourceKind === 'external';
  return <>
    <MarkdownContent components={components}>{text}</MarkdownContent>
    {selected && <div className="research-citation-backdrop" onClick={close}>
    <section ref={preview} tabIndex={-1} role="dialog" aria-modal="true" className="research-citation-preview" aria-label="引用依据"
      onClick={event => event.stopPropagation()} onKeyDown={event => {
        if (event.key === 'Escape') { event.stopPropagation(); close(); }
        if (event.key === 'Tab') {
          const items = [...event.currentTarget.querySelectorAll('button, a[href]')];
          if (event.shiftKey && (document.activeElement === items[0] || document.activeElement === event.currentTarget)) {
            event.preventDefault(); items.at(-1)?.focus();
          } else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0]?.focus(); }
        }
      }}>
      <div className="research-citation-heading"><strong>{selected.title || '引用依据'}</strong><button type="button" onClick={close}>关闭</button></div>
      {selected.unavailable ? <p>这条引用暂不能恢复，请查看报告中保存的原文依据。</p> : <>
        {selected.quote && <blockquote>{selected.quote}</blockquote>}
        <p className="theme-text-muted">{selected.accessLevel === 'abstract' ? '仅摘要' : selected.page ? `第 ${selected.page} 页`
          : selected.location?.pageResolution === 'ambiguous' ? '引文出现在多页，页码未唯一确定'
          : selected.location?.pageResolution === 'unresolved' ? '原文引文已保存，页码暂未定位' : '论文来源'}</p>
        {external && /^https:\/\/arxiv\.org\/abs\//u.test(selected.url || '') && <a href={selected.url} target="_blank" rel="noopener noreferrer">查看来源页面</a>}
        {!external && selected.pdfId && onJumpToSource && <button type="button" onClick={() => onJumpToSource({ ...selected,
          pageIndex: selected.page != null ? selected.page - 1 : selected.pageIndex })}>查看论文原文</button>}
      </>}
    </section></div>}
  </>;
}
