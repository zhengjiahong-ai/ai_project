export const createEmptyMonitorState = () => ({
  monitors: [],
  selectedMonitorId: '',
  selectedMonitor: null,
  newPapers: [],
  digest: '',
  loading: false,
  checking: false,
  error: '',
});

export const normalizeMonitor = (monitor = {}) => ({
  monitorId: `${monitor.monitorId ?? ''}`.trim(),
  question: `${monitor.question ?? ''}`.trim(),
  sources: Array.isArray(monitor.sources) ? monitor.sources : ['arxiv'],
  frequency: `${monitor.frequency ?? 'manual'}`.trim(),
  createdAt: `${monitor.createdAt ?? ''}`.trim(),
  lastChecked: `${monitor.lastChecked ?? ''}`.trim(),
  active: monitor.active !== false,
});

export const normalizeCheckResult = (result = {}) => ({
  monitorId: `${result.monitorId ?? ''}`.trim(),
  newPapers: (result.newPapers ?? []).map((p) => ({
    title: `${p.title ?? 'Untitled'}`.trim(),
    paperId: `${p.paperId ?? ''}`.trim(),
    abstract: `${p.abstract ?? ''}`.trim(),
    year: p.year ?? null,
    relevanceScore: typeof p.relevanceScore === 'number' ? p.relevanceScore : 0,
    url: `${p.url ?? ''}`.trim(),
    source: `${p.source ?? 'arxiv'}`.trim(),
  })),
  newCount: result.newCount ?? 0,
  recommended: Array.isArray(result.recommended) ? result.recommended : [],
  digest: `${result.digest ?? ''}`.trim(),
  error: `${result.error ?? ''}`.trim(),
});

export const buildCreateMonitorPayload = ({ question = '', sources = ['arxiv'], frequency = 'manual' } = {}) => ({
  question: `${question ?? ''}`.trim(),
  sources: Array.isArray(sources) ? sources.filter((s) => ['arxiv', 'pubmed'].includes(s)) : ['arxiv'],
  frequency: frequency === 'daily' ? 'daily' : 'manual',
});
