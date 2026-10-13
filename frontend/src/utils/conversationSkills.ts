export const CONVERSATION_SKILLS = [
  { id: 'read', command: '精读', description: '围绕问题、方法和实验读懂论文' },
  { id: 'background', command: '补课', description: '补齐当前理解所需的前置知识' },
  { id: 'quiz', command: '自测', description: '用自己的话解释，再获得反馈' },
  { id: 'critique', command: '批判', description: '检查贡献、假设与实验依据' },
  { id: 'compare', command: '比较', description: '对比论文的方法、实验与局限' },
  { id: 'research', command: '研究', description: '围绕开放问题综合任务材料' },
] as const;

export type ConversationSkillId = typeof CONVERSATION_SKILLS[number]['id'];
export type ComposableCapability = 'chat' | 'background' | 'critique' | 'compare';
type ResolvedSkill = { skillId: ConversationSkillId | 'compose' | 'chat'; command: string; instruction: string; steps?: ComposableCapability[] };
export type ConversationIntent = { skill: ResolvedSkill | null; clarification?: { prompt: string; choices: { label: string; skill: ResolvedSkill }[] } };

export function parseSkillCommand(input: string) {
  const match = input.trim().match(/^\/([^\s]+)(?:\s+([\s\S]*))?$/u);
  if (!match) return null;
  const skill = CONVERSATION_SKILLS.find((item) => item.command === match[1]);
  return skill ? { skillId: skill.id, command: skill.command, instruction: (match[2] || '').trim() } : null;
}

export function getSkillSuggestions(input: string) {
  const match = input.match(/^\/([^\s]*)$/u);
  return match ? CONVERSATION_SKILLS.filter((skill) => skill.command.startsWith(match[1])) : [];
}

// Only explicit action requests select a capability; mentioning its name is ordinary chat.
const INTENT_PATTERNS: [ConversationSkillId, RegExp][] = [
  ['read', /^(?:请)?(?:帮我|带我|陪我)?(?:逐步)?(?:精读|带着读|引导我阅读)/u],
  ['quiz', /^(?:请)?(?:帮我)?(?:自测|测测我|考考我|检验我的理解|检查我是否理解)/u],
  ['critique', /^(?:请)?(?:帮我)?(?:批判性阅读|批判阅读|批判分析|批判(?!这个词|一词)|分析.{0,15}(?:局限|不足|漏洞))/u],
  ['compare', /^(?:请)?(?:帮我)?(?:比较|对比)(?!这个词|一词|是什么意思)/u],
  ['background', /^(?:请)?(?:帮我)?(?:补课|补齐前置知识|补充背景知识|讲解前置知识)/u],
  ['research', /^(?:请)?(?:帮我)?(?:深入研究|深度研究|开展研究|研究一下)/u],
];

export function resolveConversationSkill(input: string) {
  const explicit = parseSkillCommand(input);
  if (explicit) return explicit;
  const text = input.trim();
  if (!text || text.startsWith('/') || /(?:是什么意思|什么意思|怎么使用)[？?。!！]*$/u.test(text)) return null;
  const id = INTENT_PATTERNS.find(([, pattern]) => pattern.test(text))?.[0];
  const skill = CONVERSATION_SKILLS.find((item) => item.id === id);
  return skill ? { skillId: skill.id, command: skill.command, instruction: text } : null;
}

/** New capabilities don't inherit the paused lesson's paper subset. */
export function startsNewCapability(skillId: ConversationSkillId | 'compose' | 'chat') {
  return ['read', 'quiz', 'critique', 'compare', 'research', 'compose', 'chat'].includes(skillId);
}

/** Plan only explicit action clauses; names in explanations never trigger work. */
export function resolveConversationIntent(input: string): ConversationIntent {
  const text = input.trim();
  const explicit = parseSkillCommand(text);
  if (explicit || text.startsWith('/')) return { skill: explicit };
  const actions: (ConversationSkillId | 'chat')[] = [];
  const clauses = text.split(/(?:[，,；;。]\s*(?=(?:请|帮我|先|首先|然后|再|最后|同时|并|以及|比较|对比|补课|补齐|分析|批判|解释|概括|精读|自测|研究|深入研究))|\s*(?:然后|接着|再来|并且|以及|同时)\s*)/u);
  for (const clause of clauses) {
    const value = clause.trim().replace(/^(?:请)?(?:帮我|给我|为我)?(?:首先|先|然后|最后|再|并)?\s*/u, '')
      .replace(/^(?:用|以)(?:一|两|二|三)句话\s*(?=解释|概括|总结)/u, '');
    if (!value || /^(?:不|别|无需|不要)/u.test(value)) continue;
    const skill = resolveConversationSkill(value);
    const action = skill?.skillId || (/^(?:解释|概括|总结)(?!这个词|一词|是什么意思)/u.test(value) ? 'chat' : null);
    if (action && !actions.includes(action)) actions.push(action);
  }
  const choose = (prompt: string, ids: (ConversationSkillId | 'chat')[]): ConversationIntent => ({
    skill: null, clarification: { prompt, choices: ids.map(id => ({
      label: id === 'chat' ? '概括与解释' : CONVERSATION_SKILLS.find(item => item.id === id)!.command,
      skill: { skillId: id, command: id === 'chat' ? '解释' : CONVERSATION_SKILLS.find(item => item.id === id)!.command,
        instruction: text },
    })) },
  });
  // Interactive learning and research have their own lifecycle. Ask which to
  // start instead of silently dropping part of a mixed request.
  if (actions.length > 1 && actions.some(id => ['read', 'quiz', 'research'].includes(id))) {
    return choose('先从哪一步开始？', actions.filter(id => id !== 'chat'));
  }
  if (actions.length > 3) return choose('一次最多组合三项，请先选择重点。', ['background', 'compare', 'critique']);
  if (actions.length > 1) return { skill: { skillId: 'compose', command: '综合分析', instruction: text, steps: actions as ComposableCapability[] } };
  if (actions.length === 0 && /^(?:请)?(?:帮我)?(?:分析|综合分析)(?:一下)?(?:[这那].*|[？?。!！]*|论文.*)$/u.test(text)) {
    return choose('希望重点看什么？', ['chat', 'critique', 'compare', 'research']);
  }
  const direct = resolveConversationSkill(text);
  if (!direct && actions.length === 1 && actions[0] !== 'chat') {
    const skill = CONVERSATION_SKILLS.find(item => item.id === actions[0])!;
    return { skill: { skillId: skill.id, command: skill.command, instruction: text } };
  }
  return { skill: direct };
}
