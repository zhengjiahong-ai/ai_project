import React, { useRef, useState } from 'react';
import WorkbenchPopover from './WorkbenchPopover';
import DocumentOrganizer from './DocumentOrganizer';
import { Save } from 'lucide-react';

export default function DocumentActions({ document, editing, dirty, saving, disabled, onEdit, onSave,
  onLocate, onRecheck, recheckDisabled, onRestore, taskId, tasks, onRename, onMove, onExport, kind = '成果', getPendingMove, displayTitle,
  researchVersions = [], onOpenVersion }) {
  const [action, setAction] = useState(null);
  const root = useRef(null);
  return <div ref={root} className="unified-document-toolbar workbench-document-actions">
    {document.origin !== 'machine' && <button type="button" onClick={onEdit}>{editing ? '完成编辑' : '编辑'}</button>}
    {researchVersions.length > 1 && <WorkbenchPopover label="研究版本" trigger={<span>版本</span>}>
      {close => <>{researchVersions.map(version => <button type="button" key={version.id || version.artifactId}
        aria-pressed={(version.id || version.artifactId) === (document.id || document.artifactId)}
        onClick={() => { onOpenVersion?.(version); close(); }}>
        {version.origin === 'machine' ? '研究原稿' : version.edited ? '我的修改稿' : '当前稿'}
        {version.createdAt && <small> · {new Date(version.createdAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })}</small>}
      </button>)}</>}
    </WorkbenchPopover>}
    {(editing || dirty) && <button type="button" className="workbench-primary" disabled={saving || disabled || !dirty} onClick={onSave}><Save size={15} />{saving ? '保存中…' : '保存'}</button>}
    {(editing || dirty || saving) && <span className="unified-document-save-state" role="status">{saving ? '正在保存' : dirty ? '未保存修改' : '已保存'}</span>}
    <WorkbenchPopover label={`${kind}更多操作`}>
      {close => <>
      {onLocate && <button type="button" onClick={() => { onLocate(); close(); }}>在对话中查看</button>}
      {onRecheck && <button type="button" disabled={recheckDisabled} onClick={() => { onRecheck(); close(); }}>重新核查</button>}
      {document.origin !== 'machine' && <button type="button" onClick={() => { close(false); setAction('rename'); }}>重命名…</button>}
      {onExport && <button type="button" onClick={() => { onExport(); close(); }}>下载 Markdown</button>}
      {document.origin !== 'machine' && <button type="button" onClick={() => { close(false); setAction('move'); }}>移到其他任务…</button>}
      {document.versions?.length > 0 && <button type="button" onClick={() => { close(false); setAction('history'); }}>历史版本（{document.versions.length}）</button>}
      </>}
    </WorkbenchPopover>
    {action && <DocumentOrganizer action={action} document={document} displayTitle={displayTitle} kind={kind} taskId={taskId} tasks={tasks} dirty={dirty || saving} disabled={saving || disabled}
      onRename={onRename} onMove={onMove} onRestore={onRestore} getPendingMove={getPendingMove} onClose={() => { setAction(null); root.current?.querySelector('.workbench-popover-trigger')?.focus(); }} />}
  </div>;
}
