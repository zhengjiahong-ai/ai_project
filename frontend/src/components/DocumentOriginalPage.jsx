import React, { useEffect, useRef, useState } from 'react';
import { taskWorkspaceApi } from '../services/taskWorkspaceApi';
import { pdfPageDataUrl } from '../utils/pdfPageExport';

export default function DocumentOriginalPage({ taskId, source, title, paperTitle, text }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState(null);
  const [exportError, setExportError] = useState('');
  const [exporting, setExporting] = useState(false);
  const dialog = useRef(null);
  const key = JSON.stringify([taskId, source.pdfId, source.pageIndex]);
  useEffect(() => {
    if (!open) return;
    let active = true;
    const abort = new AbortController();
    setState({ key, status: 'loading' });
    (async () => {
      const blob = await taskWorkspaceApi.getMaterialFile(taskId, source.pdfId);
      abort.signal.throwIfAborted();
      const image = await pdfPageDataUrl(blob, source.pageIndex, abort.signal);
      if (active) setState({ key, status: 'success', image });
    })().catch(error => {
      if (active) setState({ key, status: 'error', message: error.response?.data?.message || error.message || '原图暂时无法读取，请稍后重新展开。' });
    });
    return () => { active = false; abort.abort(); };
  }, [open, key, taskId, source.pdfId, source.pageIndex]);
  const current = state?.key === key ? state : null;
  const download = async () => {
    if (current?.status !== 'success') return;
    setExportError(''); setExporting(true);
    try {
      const { documentHtmlExport } = await import('../utils/documentHtmlExport');
      const html = documentHtmlExport({ title, text, paperTitle, ...source, image: current.image });
      const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${(title || '论文成果').replace(/[\\/:*?"<>|]/g, '_')}.html`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setExportError('图文下载未完成，请重试。'); }
    finally { setExporting(false); }
  };
  return <details className="reader-chat-citations unified-document-original" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>原图与图文下载 · 第 {source.pageIndex + 1} 页</summary>
    {open && <div>
      {current?.status === 'error' ? <p role="alert">{current.message}</p>
        : current?.status !== 'success' ? <p role="status">正在读取原图…</p>
        : <><div className="unified-document-toolbar"><button type="button" disabled={exporting} onClick={download}>{exporting ? '正在准备下载…' : '下载图文 HTML'}</button>
          <button type="button" onClick={() => dialog.current.showModal()}>放大原图</button></div>
          <img src={current.image} alt={`${paperTitle || source.pdfId}第 ${source.pageIndex + 1} 页原图`} style={{ display: 'block', width: '100%', height: 'auto', marginTop: 12 }} />
          <dialog ref={dialog} className="panoramic-image-dialog" aria-label="成果原图放大查看">
            <header><span>第 {source.pageIndex + 1} 页原图</span><button type="button" onClick={() => dialog.current.close()}>关闭</button></header>
            <div tabIndex={0} aria-label="可滚动的成果原图"><img src={current.image} alt="成果来源原图" style={{ width: 1800, maxWidth: 'none', height: 'auto' }} /></div>
          </dialog></>}
      {exportError && <p role="alert">{exportError}</p>}
    </div>}
  </details>;
}
