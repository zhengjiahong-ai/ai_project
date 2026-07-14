import { useState, useCallback, useEffect } from 'react';
import { Bell, Plus, Search, Trash2, Clock, BookOpen, ExternalLink, Star, Loader2, AlertTriangle, CheckCircle2, X, Globe, FileText } from 'lucide-react';
import { createEmptyMonitorState, normalizeMonitor, normalizeCheckResult, buildCreateMonitorPayload } from './researchMonitorModel.js';

const SOURCE_ICONS = { arxiv: FileText, pubmed: Globe };
const SOURCE_LABELS = { arxiv: 'arXiv', pubmed: 'PubMed' };

export default function ResearchMonitorPanel({ apiService, agentApiService, paperLibrary = [], onCreateAgentProject }) {
  const [state, setState] = useState(createEmptyMonitorState);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ question: '', sources: ['arxiv'], frequency: 'manual' });

  const api = agentApiService ?? apiService;

  const updateState = useCallback((patch) => setState((prev) => ({ ...prev, ...patch })), []);

  const loadMonitors = useCallback(async () => {
    updateState({ loading: true, error: '' });
    try {
      const result = await api.get('/research-monitors');
      const monitors = (result?.monitors ?? []).map(normalizeMonitor);
      updateState({ monitors, loading: false });
    } catch (err) {
      updateState({ loading: false, error: err?.message ?? 'Failed to load monitors.' });
    }
  }, [api, updateState]);

  useEffect(() => { loadMonitors(); }, [loadMonitors]);

  const handleCreate = useCallback(async () => {
    if (!createForm.question.trim()) return;
    updateState({ error: '' });
    try {
      const payload = buildCreateMonitorPayload(createForm);
      await api.post('/research-monitors', payload);
      setShowCreate(false);
      setCreateForm({ question: '', sources: ['arxiv'], frequency: 'manual' });
      await loadMonitors();
    } catch (err) {
      updateState({ error: err?.message ?? 'Failed to create monitor.' });
    }
  }, [createForm, api, loadMonitors, updateState]);

  const handleCheck = useCallback(async (monitorId) => {
    updateState({ checking: true, error: '' });
    try {
      const result = await api.get(`/research-monitors/${monitorId}/check`);
      const normalized = normalizeCheckResult(result);
      updateState({ checking: false, newPapers: normalized.newPapers, digest: normalized.digest, selectedMonitorId: monitorId });
    } catch (err) {
      updateState({ checking: false, error: err?.message ?? 'Failed to check publications.' });
    }
  }, [api, updateState]);

  const handleDeactivate = useCallback(async (monitorId) => {
    if (!window.confirm('确认停用此研究监控？')) return;
    try {
      await api.delete(`/research-monitors/${monitorId}`);
      await loadMonitors();
    } catch (err) {
      updateState({ error: err?.message ?? 'Failed to deactivate monitor.' });
    }
  }, [api, loadMonitors, updateState]);

  const handleAddToLibrary = useCallback((paper) => {
    // This will be handled by the parent component
  }, []);

  const handleDigest = useCallback(async (monitorId) => {
    updateState({ error: '' });
    try {
      const result = await api.get(`/research-monitors/${monitorId}/digest`);
      updateState({ digest: result?.digest ?? '', selectedMonitorId: monitorId });
    } catch (err) {
      updateState({ error: err?.message ?? 'Failed to get digest.' });
    }
  }, [api, updateState]);

  const formatLastChecked = (lastChecked) => {
    if (!lastChecked) return '从未检查';
    try {
      const date = new Date(lastChecked);
      const now = new Date();
      const hoursAgo = Math.round((now - date) / (1000 * 60 * 60));
      if (hoursAgo < 1) return '刚刚';
      if (hoursAgo < 24) return `${hoursAgo} 小时前`;
      return `${Math.round(hoursAgo / 24)} 天前`;
    } catch {
      return '未知';
    }
  };

  const renderStars = (score) => {
    const stars = Math.min(Math.round(score * 5), 5);
    return Array.from({ length: 5 }, (_, i) => (
      <Star key={i} size={12} className={i < stars ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300 dark:text-gray-600'} />
    ));
  };

  return (
    <div className="research-monitor-panel flex flex-col h-full">
      <div className="p-4 border-b border-pixiu-border">
        <h3 className="text-lg font-semibold text-pixiu flex items-center gap-2">
          <Bell size={20} />
          研究监控
        </h3>
        <p className="text-sm text-pixiu-muted mt-1">
          监控 arXiv / PubMed 新论文，匹配研究兴趣。
        </p>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* Create button */}
        {!showCreate && (
          <button
            className="w-full py-2 px-4 rounded bg-pixiu-accent text-white font-medium flex items-center justify-center gap-2"
            onClick={() => setShowCreate(true)}
          >
            <Plus size={18} />
            新建监控
          </button>
        )}

        {/* Create form */}
        {showCreate && (
          <div className="p-3 rounded border border-pixiu-border bg-pixiu-surface space-y-3">
            <div>
              <label className="text-sm font-medium text-pixiu">研究问题 *</label>
              <input
                className="w-full mt-1 p-2 rounded bg-pixiu-bg border border-pixiu-border text-pixiu text-sm"
                placeholder="如：retrieval-augmented generation for knowledge-intensive tasks"
                value={createForm.question}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, question: e.target.value }))}
              />
            </div>

            <div className="flex gap-3">
              <div className="flex-1">
                <label className="text-sm font-medium text-pixiu">来源</label>
                <div className="flex gap-2 mt-1">
                  {['arxiv', 'pubmed'].map((src) => (
                    <button
                      key={src}
                      className={`px-3 py-1 rounded text-xs font-medium border ${
                        createForm.sources.includes(src)
                          ? 'bg-pixiu-accent text-white border-pixiu-accent'
                          : 'bg-pixiu-bg text-pixiu-muted border-pixiu-border'
                      }`}
                      onClick={() =>
                        setCreateForm((prev) => ({
                          ...prev,
                          sources: prev.sources.includes(src)
                            ? prev.sources.filter((s) => s !== src)
                            : [...prev.sources, src],
                        }))
                      }
                    >
                      {SOURCE_LABELS[src]}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-sm font-medium text-pixiu">频率</label>
                <select
                  className="w-full mt-1 p-2 rounded bg-pixiu-bg border border-pixiu-border text-pixiu text-sm"
                  value={createForm.frequency}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, frequency: e.target.value }))}
                >
                  <option value="manual">手动检查</option>
                  <option value="daily">每日</option>
                </select>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                className="flex-1 py-2 rounded bg-pixiu-accent text-white text-sm font-medium"
                onClick={handleCreate}
                disabled={!createForm.question.trim()}
              >
                创建
              </button>
              <button
                className="px-3 py-2 rounded border border-pixiu-border text-pixiu-muted text-sm flex items-center gap-1"
                onClick={() => { setShowCreate(false); setCreateForm({ question: '', sources: ['arxiv'], frequency: 'manual' }); }}
              >
                <X size={14} /> 取消
              </button>
            </div>
          </div>
        )}

        {/* Error */}
        {state.error && (
          <div className="p-3 rounded bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400 flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <span>{state.error}</span>
          </div>
        )}

        {/* Monitor list */}
        {state.monitors.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold text-pixiu">活跃监控 ({state.monitors.length})</h4>
            {state.monitors.map((monitor) => (
              <div key={monitor.monitorId} className="rounded border border-pixiu-border p-3 space-y-2">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-pixiu truncate">{monitor.question}</p>
                    <div className="flex items-center gap-2 mt-1 text-xs text-pixiu-muted">
                      {monitor.sources.map((src) => {
                        const Icon = SOURCE_ICONS[src] ?? Globe;
                        return (
                          <span key={src} className="flex items-center gap-1">
                            <Icon size={12} /> {SOURCE_LABELS[src] ?? src}
                          </span>
                        );
                      })}
                      <span className="flex items-center gap-1">
                        <Clock size={12} /> {formatLastChecked(monitor.lastChecked)}
                      </span>
                    </div>
                  </div>
                  <button
                    className="p-1 hover:bg-pixiu-surface rounded text-pixiu-muted"
                    onClick={() => handleDeactivate(monitor.monitorId)}
                    title="停用"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                <div className="flex gap-2">
                  <button
                    className="flex items-center gap-1 px-2 py-1 rounded bg-pixiu-surface border border-pixiu-border text-pixiu text-xs"
                    onClick={() => handleCheck(monitor.monitorId)}
                    disabled={state.checking}
                  >
                    {state.checking && state.selectedMonitorId === monitor.monitorId ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <Search size={12} />
                    )}
                    检查新论文
                  </button>
                  <button
                    className="flex items-center gap-1 px-2 py-1 rounded bg-pixiu-surface border border-pixiu-border text-pixiu text-xs"
                    onClick={() => handleDigest(monitor.monitorId)}
                  >
                    <BookOpen size={12} />
                    摘要
                  </button>
                </div>

                {/* Check results */}
                {state.selectedMonitorId === monitor.monitorId && state.newPapers.length > 0 && (
                  <div className="border-t border-pixiu-border pt-2 space-y-1">
                    <p className="text-xs font-medium text-pixiu">
                      发现 {state.newPapers.length} 篇新论文
                    </p>
                    {state.newPapers.slice(0, 10).map((paper, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs p-1.5 rounded hover:bg-pixiu-surface/50">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1 mb-0.5">
                            {renderStars(paper.relevanceScore)}
                            <span className="text-pixiu-muted font-mono">{paper.relevanceScore.toFixed(2)}</span>
                          </div>
                          <p className="font-medium text-pixiu truncate">{paper.title}</p>
                          {paper.year && <span className="text-pixiu-muted mr-2">{paper.year}</span>}
                          {paper.abstract && (
                            <p className="text-pixiu-muted mt-0.5 line-clamp-2">{paper.abstract.slice(0, 200)}</p>
                          )}
                        </div>
                        {paper.url && (
                          <a
                            href={paper.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1 text-pixiu-muted hover:text-pixiu-accent shrink-0"
                          >
                            <ExternalLink size={12} />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Digest */}
        {state.digest && (
          <div className="p-3 rounded border border-pixiu-border bg-pixiu-surface">
            <h4 className="text-sm font-semibold text-pixiu mb-2">研究摘要</h4>
            <div className="prose prose-sm max-w-none text-pixiu whitespace-pre-wrap">
              {state.digest}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!state.loading && state.monitors.length === 0 && !showCreate && (
          <div className="text-center py-8 text-pixiu-muted">
            <Bell size={32} className="mx-auto mb-2 opacity-40" />
            <p className="text-sm">暂无研究监控</p>
            <p className="text-xs mt-1">创建监控以自动跟踪 arXiv / PubMed 新论文</p>
          </div>
        )}

        {state.loading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={24} className="animate-spin text-pixiu-muted" />
          </div>
        )}
      </div>
    </div>
  );
}
