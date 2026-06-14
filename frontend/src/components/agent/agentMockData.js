export const agentPapers = [
  {
    id: 'rag',
    title: 'Retrieval-Augmented Generation for Knowledge-Intensive NLP',
    year: '2020',
    status: '已索引',
    tags: ['RAG', '证据追溯', '知识增强'],
  },
  {
    id: 'self-rag',
    title: 'Self-RAG: Learning to Retrieve, Generate and Critique',
    year: '2023',
    status: '已解析',
    tags: ['自我批判', '检索生成', '可信回答'],
  },
  {
    id: 'toolformer',
    title: 'Toolformer: Language Models Can Teach Themselves to Use Tools',
    year: '2023',
    status: '待分析',
    tags: ['工具调用', '任务执行'],
  },
];

export const agentQuickTasks = ['方法对比', '创新点总结', '局限性分析', '生成综述', '阅读计划'];

export const agentPlanSteps = [
  { id: 'scope', label: '确认研究范围', detail: '根据选中的论文和任务确定分析边界。', status: 'done' },
  { id: 'retrieve', label: '检索关键证据', detail: '从方法、实验和结论章节召回相关片段。', status: 'done' },
  { id: 'compare', label: '生成跨论文对比', detail: '整理研究问题、方法设计和局限性差异。', status: 'running' },
  { id: 'answer', label: '输出研究结论', detail: '形成可继续追问的结构化回答。', status: 'waiting' },
];

export const agentToolCalls = [
  {
    id: 'rag-search',
    name: 'RAG 检索',
    status: '完成',
    target: '研究问题 + 方法设计',
    result: '命中 12 条相关证据片段',
  },
  {
    id: 'critical-reading',
    name: '批判性阅读',
    status: '运行中',
    target: '实验指标与结论边界',
    result: '正在检查结论是否过度外推',
  },
  {
    id: 'background',
    name: '背景补课',
    status: '完成',
    target: 'RAG / Tool Use / Agent 基础概念',
    result: '生成概念关系摘要',
  },
  {
    id: 'deep-research',
    name: '深度研究',
    status: '排队中',
    target: '综述草稿与后续阅读建议',
    result: '等待证据汇总后生成',
  },
];

export const agentEvidenceItems = [
  {
    id: 'evidence-rag',
    paper: 'Retrieval-Augmented Generation for Knowledge-Intensive NLP',
    location: 'Methods · p.3',
    quote: '模型通过检索外部知识片段来增强生成过程，使回答能够绑定到可检查的来源。',
  },
  {
    id: 'evidence-self-rag',
    paper: 'Self-RAG: Learning to Retrieve, Generate and Critique',
    location: 'Approach · p.5',
    quote: '系统在检索、生成和自我批判之间形成显式流程，用于降低无证据生成。',
  },
  {
    id: 'evidence-toolformer',
    paper: 'Toolformer',
    location: 'Training · p.4',
    quote: '语言模型可以学习何时调用外部工具，并将工具结果整合回文本生成。',
  },
];
