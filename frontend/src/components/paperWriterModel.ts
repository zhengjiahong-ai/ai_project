export type SectionKey =
  | 'abstract'
  | 'introduction'
  | 'relatedWork'
  | 'methodology'
  | 'results'
  | 'discussion'
  | 'conclusion';

export interface PaperWriterState {
  question: string;
  title: string;
  selectedSourceIds: string[];
  status: string;
  sections: Partial<Record<SectionKey, string>>;
  currentSection: string;
  progress: number;
  referenceCount: number;
  outputFiles: unknown;
  error: string;
}

export interface PaperDraftResult {
  question: string;
  title: string;
  status: string;
  sections: Partial<Record<SectionKey, string>>;
  draftedCount: number;
  currentSection: string;
  progress: number;
  referenceCount: number;
  outputFiles: unknown;
  markdown: string;
  latex: string;
  bibtex: string;
  error: string;
}

export interface PaperDraftPayload {
  question: string;
  title: string;
  findings: unknown[];
  evidenceItems: unknown[];
  conflicts: unknown[];
  sourceIds: string[];
}

export const SECTIONS: SectionKey[] = [
  'abstract',
  'introduction',
  'relatedWork',
  'methodology',
  'results',
  'discussion',
  'conclusion',
];

export const SECTION_LABELS: Record<SectionKey, string> = {
  abstract: 'Abstract',
  introduction: 'Introduction',
  relatedWork: 'Related Work',
  methodology: 'Methodology',
  results: 'Results',
  discussion: 'Discussion',
  conclusion: 'Conclusion',
};

export const createEmptyPaperWriterState = (): PaperWriterState => ({
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

export const normalizePaperDraftResult = (result: Record<string, unknown> = {}): PaperDraftResult => {
  const sections: Partial<Record<SectionKey, string>> = {};
  const raw = (result?.sections ?? result?.draft ?? {}) as Record<string, unknown>;
  for (const key of SECTIONS) {
    sections[key] = typeof raw[key] === 'string' ? raw[key] : '';
  }
  const draftedSections = SECTIONS.filter((k) => sections[k]);
  return {
    question: `${result?.question ?? ''}`.trim(),
    title: `${result?.title ?? ''}`.trim(),
    status: result?.status === 'success' ? 'done' : result?.status === 'error' ? 'error' : (result?.status as string) ?? 'idle',
    sections,
    draftedCount: draftedSections.length,
    currentSection: draftedSections.length > 0 ? draftedSections[draftedSections.length - 1] : '',
    progress: draftedSections.length / SECTIONS.length,
    referenceCount: (result?.referenceCount as number) ?? 0,
    outputFiles: result?.outputFiles ?? null,
    markdown: (result?.markdown as string) ?? '',
    latex: (result?.latex as string) ?? '',
    bibtex: (result?.bibtex as string) ?? '',
    error: `${result?.error ?? ''}`.trim(),
  };
};

export const buildPaperDraftPayload = ({
  question = '',
  title = '',
  sourceIds = [],
  findings = [],
  evidenceItems = [],
  conflicts = [],
}: {
  question?: string;
  title?: string;
  sourceIds?: string[];
  findings?: Record<string, unknown>[];
  evidenceItems?: Record<string, unknown>[];
  conflicts?: Record<string, unknown>[];
} = {}): PaperDraftPayload => ({
  question: `${question ?? ''}`.trim(),
  title: `${title ?? ''}`.trim(),
  findings: Array.isArray(findings) ? findings : [],
  evidenceItems: Array.isArray(evidenceItems) ? evidenceItems : [],
  conflicts: Array.isArray(conflicts) ? conflicts : [],
  sourceIds: Array.isArray(sourceIds) ? sourceIds.filter(Boolean) : [],
});

export const buildRegenerateSectionPayload = ({
  question = '',
  title = '',
  section = '',
  findings = [],
  evidenceItems = [],
  conflicts = [],
  existingSections = {},
}: {
  question?: string;
  title?: string;
  section?: string;
  findings?: Record<string, unknown>[];
  evidenceItems?: Record<string, unknown>[];
  conflicts?: Record<string, unknown>[];
  existingSections?: Record<string, string>;
} = {}) => ({
  question: `${question ?? ''}`.trim(),
  title: `${title ?? ''}`.trim(),
  section,
  findings: Array.isArray(findings) ? findings : [],
  evidenceItems: Array.isArray(evidenceItems) ? evidenceItems : [],
  conflicts: Array.isArray(conflicts) ? conflicts : [],
  existingSections: existingSections || {},
});
