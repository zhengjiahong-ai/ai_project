export const SECTIONS = [
  'abstract',
  'introduction',
  'relatedWork',
  'methodology',
  'results',
  'discussion',
  'conclusion',
];

export const SECTION_LABELS = {
  abstract: 'Abstract',
  introduction: 'Introduction',
  relatedWork: 'Related Work',
  methodology: 'Methodology',
  results: 'Results',
  discussion: 'Discussion',
  conclusion: 'Conclusion',
};

export const createEmptyPaperWriterState = () => ({
  question: '',
  title: '',
  selectedSourceIds: [],
  status: 'idle',
  sections: {},
  currentSection: '',
  progress: 0,
  referenceCount: 0,
  outputFiles: null,
  error: '',
});

export const normalizePaperDraftResult = (result = {}) => {
  const sections = {};
  const raw = result?.sections ?? result?.draft ?? {};
  for (const key of SECTIONS) {
    sections[key] = typeof raw[key] === 'string' ? raw[key] : '';
  }
  const draftedSections = SECTIONS.filter((k) => sections[k]);
  return {
    question: `${result?.question ?? ''}`.trim(),
    title: `${result?.title ?? ''}`.trim(),
    status: result?.status === 'success' ? 'done' : result?.status === 'error' ? 'error' : result?.status ?? 'idle',
    sections,
    draftedCount: draftedSections.length,
    currentSection: draftedSections.length > 0 ? draftedSections[draftedSections.length - 1] : '',
    progress: draftedSections.length / SECTIONS.length,
    referenceCount: result?.referenceCount ?? 0,
    outputFiles: result?.outputFiles ?? null,
    markdown: result?.markdown ?? '',
    latex: result?.latex ?? '',
    bibtex: result?.bibtex ?? '',
    error: `${result?.error ?? ''}`.trim(),
  };
};

export const buildPaperDraftPayload = ({ question = '', title = '', sourceIds = [] } = {}) => ({
  question: `${question ?? ''}`.trim(),
  title: `${title ?? ''}`.trim(),
  findings: [],
  evidenceItems: [],
  conflicts: [],
  sourceIds: Array.isArray(sourceIds) ? sourceIds.filter(Boolean) : [],
});
