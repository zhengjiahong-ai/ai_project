import { useState, useCallback, useEffect, useRef } from 'react';
import { FileText, Download, Loader2, CheckCircle2, AlertTriangle, ChevronDown, ChevronRight, Edit3, RefreshCw, X } from 'lucide-react';
import MarkdownContent from './MarkdownContent.jsx';
import { SECTION_LABELS, SECTIONS, createEmptyPaperWriterState, normalizePaperDraftResult, buildPaperDraftPayload, buildRegenerateSectionPayload } from './paperWriterModel.ts';

export default function PaperWriterPanel({ apiService, agentApiService, currentRun, onSaveToWorkbench }) {
  const [state, setState] = useState(createEmptyPaperWriterState);
  const [expandedSections, setExpandedSections] = useState({});
  const [editingSection, setEditingSection] = useState(null);
  const [editContent, setEditContent] = useState('');
  const [regeneratingSection, setRegeneratingSection] = useState(null);
  const abortRef = useRef(null);

  const api = agentApiService ?? apiService;

  const updateState = useCallback((patch) => setState((prev) => ({ ...prev, ...patch })), []);

  // Pre-fill from Agent run results when currentRun changes
  useEffect(() => {
    if (!currentRun?.prompt) return;
    const findings = currentRun?.findings || currentRun?.artifacts?.findings || [];
    const evidenceItems = currentRun?.evidenceItems || currentRun?.artifacts?.evidenceItems || [];
    const conflicts = currentRun?.conflicts || currentRun?.artifacts?.conflicts || [];
    if (findings.length > 0 || conflicts.length > 0) {
      setState((prev) => ({
        ...prev,
        question: currentRun.prompt || prev.question,
        selectedSourceIds: evidenceItems.map((e) => e?.sourceId).filter(Boolean),
      }));
      // Store agent data for next generate
      window.__pixiuAgentDraftData = { findings, evidenceItems, conflicts };
    }
  }, [currentRun?.runId]);  // eslint-disable-line react-hooks/exhaustive-deps

  const handleRegenerateSection = useCallback(async (sectionKey) => {
    if (!state.question.trim() || !sectionKey) return;
    setRegeneratingSection(sectionKey);

    try {
      const agentData = window.__pixiuAgentDraftData || {};
      const payload = buildRegenerateSectionPayload({
        question: state.question,
        title: state.title,
        section: sectionKey,
        findings: agentData.findings || [],
        evidenceItems: agentData.evidenceItems || [],
        conflicts: agentData.conflicts || [],
        existingSections: state.sections || {},
      });

      const response = await api.generatePaperDraft(payload);
      const result = normalizePaperDraftResult(response);
      if (result.status === 'done' && result.sections[sectionKey]) {
        setState((prev) => ({
          ...prev,
          sections: { ...prev.sections, [sectionKey]: result.sections[sectionKey] },
        }));
      }
    } catch (err) {
      console.error('Section regeneration failed', err);
    } finally {
      setRegeneratingSection(null);
    }
  }, [state.question, state.title, state.sections, api]);

  const handleGenerate = useCallback(async () => {
    if (!state.question.trim()) return;
    updateState({ status: 'generating', error: '', sections: {}, currentSection: '' });

    try {
      const controller = new AbortController();
      abortRef.current = controller;

      const agentData = window.__pixiuAgentDraftData || {};
      const payload = buildPaperDraftPayload({
        question: state.question,
        title: state.title,
        sourceIds: state.selectedSourceIds,
        findings: agentData.findings || [],
        evidenceItems: agentData.evidenceItems || [],
        conflicts: agentData.conflicts || [],
      });

      const result = await api.post('/generate-paper-draft', payload, {
        signal: controller.signal,
      });

      const normalized = normalizePaperDraftResult(result);
      updateState({
        status: normalized.status,
        sections: normalized.sections,
        currentSection: normalized.currentSection,
        progress: normalized.progress,
        referenceCount: normalized.referenceCount,
        markdown: normalized.markdown,
        latex: normalized.latex,
        bibtex: normalized.bibtex,
        error: normalized.error,
      });
    } catch (err) {
      if (err?.name === 'CanceledError' || err?.message === 'canceled') return;
      updateState({ status: 'error', error: err?.message ?? 'Failed to generate paper draft.' });
    }
  }, [state.question, state.title, state.selectedSourceIds, api, updateState]);

  const handleDownload = useCallback((format) => {
    const contentMap = { md: state.markdown, tex: state.latex, bib: state.bibtex };
    const extMap = { md: 'md', tex: 'tex', bib: 'bib' };
    const mimeMap = { md: 'text/markdown', tex: 'text/plain', bib: 'text/plain' };

    const content = contentMap[format];
    if (!content) return;

    const blob = new Blob([content], { type: mimeMap[format] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(state.title || 'paper').replace(/[^a-zA-Z0-9一-鿿_-]/g, '_')}.${extMap[format]}`;
    a.click();
    URL.revokeObjectURL(url);
  }, [state.markdown, state.latex, state.bibtex, state.title]);

  const toggleSection = useCallback((key) => {
    setExpandedSections((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const startEditSection = useCallback((key) => {
    setEditingSection(key);
    setEditContent(state.sections[key] ?? '');
  }, [state.sections]);

  const saveEditSection = useCallback(() => {
    if (editingSection) {
      setState((prev) => ({
        ...prev,
        sections: { ...prev.sections, [editingSection]: editContent },
      }));
    }
    setEditingSection(null);
    setEditContent('');
  }, [editingSection, editContent]);

  const handleSaveToWorkbench = useCallback(() => {
    if (onSaveToWorkbench && state.markdown) {
      onSaveToWorkbench({
        type: 'paper_draft',
        title: state.title || '论文草稿',
        content: state.markdown,
        metadata: { question: state.question, sections: state.sections },
      });
    }
  }, [onSaveToWorkbench, state.markdown, state.title, state.question, state.sections]);

  const draftedSections = SECTIONS.filter((k) => state.sections[k]);
  const isGenerating = state.status === 'generating';

  return (
    <div className="paper-writer-panel flex flex-col h-full">
      <div className="paper-writer-header p-4 border-b border-pixiu-border">
        <h3 className="text-lg font-semibold text-pixiu flex items-center gap-2">
          <FileText size={20} />
          论文写作
        </h3>
        <p className="text-sm text-pixiu-muted mt-1">
          基于研究成果自动生成学术论文草稿，支持 Markdown / LaTeX / BibTeX 导出。
        </p>
      </div>

      <div className="paper-writer-body flex-1 overflow-auto p-4 space-y-4">
        {/* Input area */}
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium text-pixiu">研究问题 *</label>
            <textarea
              className="w-full mt-1 p-2 rounded bg-pixiu-surface border border-pixiu-border text-pixiu text-sm resize-none"
              rows={3}
              placeholder="输入研究问题，如：对比 RAG 与 Self-RAG 在开放域问答中的性能..."
              value={state.question}
              onChange={(e) => updateState({ question: e.target.value })}
              disabled={isGenerating}
            />
          </div>
          <div>
            <label className="text-sm font-medium text-pixiu">论文标题（可选）</label>
            <input
              className="w-full mt-1 p-2 rounded bg-pixiu-surface border border-pixiu-border text-pixiu text-sm"
              placeholder="留空则自动生成标题"
              value={state.title}
              onChange={(e) => updateState({ title: e.target.value })}
              disabled={isGenerating}
            />
          </div>
        </div>

        {/* Generate button */}
        <button
          className="w-full py-2 px-4 rounded bg-pixiu-accent text-white font-medium disabled:opacity-50 flex items-center justify-center gap-2"
          onClick={handleGenerate}
          disabled={isGenerating || !state.question.trim()}
        >
          {isGenerating ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              正在生成...
            </>
          ) : (
            <>
              <Edit3 size={18} />
              生成论文草稿
            </>
          )}
        </button>

        {/* Progress */}
        {isGenerating && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-pixiu-muted">
              <span>生成进度</span>
              <span>{Math.round(state.progress * 100)}%</span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-pixiu-surface">
              <div
                className="h-1.5 rounded-full bg-pixiu-accent transition-all duration-500"
                style={{ width: `${Math.round(state.progress * 100)}%` }}
              />
            </div>
          </div>
        )}

        {/* Section preview */}
        {draftedSections.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold text-pixiu">草稿预览</h4>
            {SECTIONS.map((key) => {
              const content = state.sections[key];
              if (!content) return null;
              const isExpanded = expandedSections[key] ?? false;
              const isEditing = editingSection === key;

              return (
                <div key={key} className="rounded border border-pixiu-border overflow-hidden">
                  <button
                    className="w-full flex items-center justify-between p-3 hover:bg-pixiu-surface/50 text-left"
                    onClick={() => toggleSection(key)}
                  >
                    <span className="text-sm font-medium text-pixiu">
                      {SECTION_LABELS[key]}
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        className="p-1 hover:bg-pixiu-surface rounded"
                        onClick={(e) => { e.stopPropagation(); handleRegenerateSection(key); }}
                        title="重新生成本节"
                        disabled={regeneratingSection === key}
                      >
                        {regeneratingSection === key ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                      </button>
                      <button
                        className="p-1 hover:bg-pixiu-surface rounded"
                        onClick={(e) => { e.stopPropagation(); startEditSection(key); }}
                        title="编辑"
                      >
                        <Edit3 size={14} />
                      </button>
                      {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </div>
                  </button>
                  {isExpanded && (
                    <div className="p-3 border-t border-pixiu-border">
                      {isEditing ? (
                        <div className="space-y-2">
                          <textarea
                            className="w-full p-2 rounded bg-pixiu-surface border border-pixiu-border text-pixiu text-sm resize-none"
                            rows={6}
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                          />
                          <div className="flex gap-2">
                            <button
                              className="px-3 py-1 rounded bg-pixiu-accent text-white text-xs"
                              onClick={saveEditSection}
                            >
                              保存
                            </button>
                            <button
                              className="px-3 py-1 rounded bg-pixiu-surface text-pixiu-muted text-xs flex items-center gap-1"
                              onClick={() => { setEditingSection(null); setEditContent(''); }}
                            >
                              <X size={12} /> 取消
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="prose prose-sm max-w-none text-pixiu">
                          <MarkdownContent content={content} />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Error */}
        {state.error && (
          <div className="p-3 rounded bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400 flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <span>{state.error}</span>
          </div>
        )}

        {/* Done state */}
        {state.status === 'done' && (
          <div className="space-y-2">
            <div className="p-3 rounded bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-sm text-green-700 dark:text-green-400 flex items-center gap-2">
              <CheckCircle2 size={16} />
              <span>草稿生成完成，共 {state.referenceCount} 条引用。</span>
            </div>

            <div className="flex gap-2 flex-wrap">
              <button
                className="flex items-center gap-1.5 px-3 py-2 rounded bg-pixiu-surface border border-pixiu-border text-pixiu text-sm hover:bg-pixiu-border/30"
                onClick={() => handleDownload('md')}
              >
                <Download size={16} /> Markdown
              </button>
              <button
                className="flex items-center gap-1.5 px-3 py-2 rounded bg-pixiu-surface border border-pixiu-border text-pixiu text-sm hover:bg-pixiu-border/30"
                onClick={() => handleDownload('tex')}
                disabled={!state.latex}
              >
                <Download size={16} /> LaTeX
              </button>
              <button
                className="flex items-center gap-1.5 px-3 py-2 rounded bg-pixiu-surface border border-pixiu-border text-pixiu text-sm hover:bg-pixiu-border/30"
                onClick={() => handleDownload('bib')}
                disabled={!state.bibtex}
              >
                <Download size={16} /> BibTeX
              </button>
              {onSaveToWorkbench && (
                <button
                  className="flex items-center gap-1.5 px-3 py-2 rounded bg-pixiu-accent text-white text-sm"
                  onClick={handleSaveToWorkbench}
                >
                  保存到工作台
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
