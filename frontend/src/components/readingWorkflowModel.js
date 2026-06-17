const normalizeTabId = (value) => `${value ?? ''}`.trim() || 'chat';

const createTabSuggestion = ({ title, description, label, tabId, tone = 'secondary' }) => ({
  title,
  description,
  label,
  tone,
  action: {
    type: 'tab',
    tabId,
  },
});

const createWorkbenchSuggestion = ({ title, description, label = '查看资产沉淀' }) => ({
  title,
  description,
  label,
  tone: 'secondary',
  action: {
    type: 'workbench',
    tabId: 'notes',
  },
});

const createAgentSuggestion = (pdfId, overrides = {}) => {
  const normalizedPdfId = `${pdfId ?? ''}`.trim();
  if (!normalizedPdfId) return null;

  return {
    title: overrides.title || '加入 Agent 项目',
    description: overrides.description || '把当前论文带入 Agent 研究区，作为跨论文比较或后续项目的起点。',
    label: overrides.label || '进入 Agent 研究',
    tone: 'agent',
    action: {
      type: 'agent',
      pdfId: normalizedPdfId,
    },
  };
};

const compactSuggestions = (items) => items.filter(Boolean).slice(0, 3);

export const buildReadingWorkflowSuggestions = ({
  hasPdf = false,
  activeTab = 'chat',
  isDeconstructing = false,
  latestUserMessage = null,
  deepResearchState = null,
  artifactCount = 0,
  pdfId = '',
} = {}) => {
  if (!hasPdf) {
    return [
      {
        title: '先上传一篇论文',
        description: '上传后系统会自动进入篇章解构，并把后续阅读、问答、批判和沉淀串成一条流程。',
        label: '',
        tone: 'secondary',
        action: null,
      },
    ];
  }

  if (isDeconstructing) {
    return compactSuggestions([
      createTabSuggestion({
        title: '正在生成论文骨架',
        description: '先查看篇章解构，等结构出来后再顺着章节继续读。',
        label: '查看篇章解构',
        tabId: 'deconstruct',
        tone: 'primary',
      }),
      createTabSuggestion({
        title: '先做一句问答',
        description: '如果已经看到关键段落，可以先用问答记录当前疑问。',
        label: '先做一句问答',
        tabId: 'chat',
      }),
    ]);
  }

  const tabId = normalizeTabId(activeTab);
  const agentSuggestion = createAgentSuggestion(pdfId);

  switch (tabId) {
    case 'deconstruct':
      return compactSuggestions([
        createTabSuggestion({
          title: '框架已可见，建议继续推进',
          description: '先用问答确认核心概念，再切换到批判阅读检查论证边界。',
          label: '进入问答',
          tabId: 'chat',
          tone: 'primary',
        }),
        createTabSuggestion({
          title: '检查论文论证',
          description: '从结构进入批判阅读，查看主张、贡献和缺失证据。',
          label: '开始批判阅读',
          tabId: 'analysis',
        }),
        agentSuggestion,
      ]);
    case 'chat':
      return compactSuggestions([
        createTabSuggestion({
          title: '当前问题已经接近阅读现场',
          description: latestUserMessage?.content
            ? '问题涉及概念背景时，先补课能减少后续误读。'
            : '先问一个最想弄明白的问题，再把答案接回论文结构。',
          label: '去补背景',
          tabId: 'background',
          tone: 'primary',
        }),
        createTabSuggestion({
          title: '直接检查论证',
          description: '如果问题已经指向论文贡献或证据，适合转入批判阅读。',
          label: '直接批判阅读',
          tabId: 'analysis',
        }),
        agentSuggestion,
      ]);
    case 'translation':
      return compactSuggestions([
        createTabSuggestion({
          title: '译文适合配合原文一起看',
          description: '读完这一页后回到问答，把局部理解放回原文上下文。',
          label: '回到问答',
          tabId: 'chat',
          tone: 'primary',
        }),
        createTabSuggestion({
          title: '回到论文结构',
          description: '用篇章解构确认当前页属于哪一段论证。',
          label: '回到篇章解构',
          tabId: 'deconstruct',
        }),
        agentSuggestion,
      ]);
    case 'background':
      return compactSuggestions([
        createTabSuggestion({
          title: '背景补齐后就能继续深读',
          description: '把概念理解转成可回答的问题，进入引导学习更稳。',
          label: '进入引导学习',
          tabId: 'socratic',
          tone: 'primary',
        }),
        createTabSuggestion({
          title: '进入批判阅读',
          description: '用补齐后的背景检查作者主张是否有足够证据。',
          label: '去批判阅读',
          tabId: 'analysis',
        }),
        agentSuggestion,
      ]);
    case 'socratic':
      return compactSuggestions([
        createTabSuggestion({
          title: '现在适合把理解变成判断',
          description: '把刚刚的回答整理成可检验观点，再检查它是否站得住。',
          label: '查看批判阅读',
          tabId: 'analysis',
          tone: 'primary',
        }),
        createTabSuggestion({
          title: '追溯关键证据',
          description: '对仍不确定的问题发起单论文 Deep Research。',
          label: '发起深度研究',
          tabId: 'deep-research',
        }),
        agentSuggestion,
      ]);
    case 'analysis':
      return compactSuggestions([
        createTabSuggestion({
          title: '批判已经开始，适合进一步深挖',
          description: '把可疑结论带到 Deep Research 里追溯证据链与相关工作。',
          label: '发起深度研究',
          tabId: 'deep-research',
          tone: 'primary',
        }),
        createWorkbenchSuggestion({
          title: '沉淀当前判断',
          description: '把批判阅读里的主张、风险和证据整理到工作台。',
          label: '沉淀为工作台卡片',
        }),
        createAgentSuggestion(pdfId, {
          title: '进入跨论文比较',
          description: '把当前论文加入 Agent 项目，后续可比较方法、指标和局限。',
          label: '进入 Agent 比较',
        }),
      ]);
    case 'deep-research': {
      const hasFindings = (deepResearchState?.task?.findings || []).length > 0;
      return compactSuggestions([
        createTabSuggestion({
          title: hasFindings ? '研究结果适合回流到阅读链路' : '先回到批判阅读确认问题',
          description: hasFindings
            ? '用批判阅读核对 findings 的结论边界和缺证据位置。'
            : 'Deep Research 前先明确要追溯的主张或证据缺口。',
          label: '回到批判阅读',
          tabId: 'analysis',
          tone: 'primary',
        }),
        createWorkbenchSuggestion({
          title: artifactCount > 0 ? '整理已有资产' : '沉淀研究发现',
          description: '把 findings、证据和开放问题保存到工作台，方便后续复用。',
        }),
        createAgentSuggestion(pdfId, {
          title: '扩展到 Agent 研究',
          description: '把当前论文作为起点，进入 Agent 工作区继续做跨论文比较。',
          label: '进入 Agent 研究',
        }),
      ]);
    }
    case 'notes':
      return compactSuggestions([
        createTabSuggestion({
          title: '资产已经可以复用',
          description: '回到篇章解构，把已沉淀的观点重新定位到论文结构中。',
          label: '回到阅读',
          tabId: 'deconstruct',
          tone: 'primary',
        }),
        createTabSuggestion({
          title: '继续追问',
          description: '围绕已有卡片或边注继续问答，补齐解释和引用。',
          label: '继续问答',
          tabId: 'chat',
        }),
        createAgentSuggestion(pdfId, {
          title: '进入多论文研究',
          description: '把当前论文和已有沉淀带到 Agent 项目中，准备后续比较。',
          label: '进入 Agent 研究',
        }),
      ]);
    default:
      return compactSuggestions([
        createTabSuggestion({
          title: '继续沿着阅读主线推进',
          description: '回到篇章解构，确认当前论文的整体位置。',
          label: '回到篇章解构',
          tabId: 'deconstruct',
          tone: 'primary',
        }),
        createTabSuggestion({
          title: '查看问答',
          description: '用问答把当前疑问接回原文证据。',
          label: '查看问答',
          tabId: 'chat',
        }),
        agentSuggestion,
      ]);
  }
};

export const getPrimaryReadingWorkflowSuggestion = (suggestions = []) =>
  (Array.isArray(suggestions) ? suggestions : []).find((item) => item?.action) || null;
