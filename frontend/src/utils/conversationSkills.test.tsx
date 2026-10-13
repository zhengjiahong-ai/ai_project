import { describe, expect, it } from 'vitest';
import { getSkillSuggestions, parseSkillCommand, resolveConversationSkill, resolveConversationIntent, startsNewCapability } from './conversationSkills';

describe('conversation skill commands', () => {
  it('preserves instructions and only parses a leading complete command', () => {
    expect(parseSkillCommand('/精读 帮我理解方法\n重点解释公式')).toEqual({ skillId: 'read', command: '精读', instruction: '帮我理解方法\n重点解释公式' });
    expect(parseSkillCommand('请解释 /研究 的意思')).toBeNull();
    expect(parseSkillCommand('/研究生')).toBeNull();
  });
  it('offers discovery without treating ordinary text as commands', () => {
    expect(getSkillSuggestions('/')).toHaveLength(6);
    expect(getSkillSuggestions('/比').map((skill) => skill.id)).toEqual(['compare']);
    expect(getSkillSuggestions('/比较 A 和 B')).toEqual([]);
    expect(getSkillSuggestions('研究')).toEqual([]);
  });
  it('routes explicit natural-language actions to the same capability as commands', () => {
    expect(resolveConversationSkill('带我精读这篇论文')?.skillId).toBe('read');
    expect(resolveConversationSkill('请帮我比较两篇论文的方法')?.skillId).toBe('compare');
    expect(resolveConversationSkill('考考我')?.skillId).toBe('quiz');
    expect(resolveConversationSkill('帮我补齐前置知识')?.skillId).toBe('background');
    expect(resolveConversationSkill('请帮我分析这篇的局限')?.skillId).toBe('critique');
    expect(resolveConversationSkill('深入研究这个方向')?.skillId).toBe('research');
    expect(resolveConversationSkill('/比较 A B')).toEqual(parseSkillCommand('/比较 A B'));
  });
  it('does not turn terminology questions or negated actions into workflows', () => {
    for (const input of ['比较是什么意思？', '深度研究怎么使用', '不需要精读', '论文使用了比较学习', '/未知命令']) {
      expect(resolveConversationSkill(input)).toBeNull();
    }
  });
  it('keeps background detours scoped to a lesson while new comparisons leave it', () => {
    expect(startsNewCapability('background')).toBe(false);
    expect(startsNewCapability('compare')).toBe(true);
    expect(startsNewCapability('read')).toBe(true);
  });

  it('composes explicit action clauses in order without starting a research job', () => {
    expect(resolveConversationIntent('请先补齐前置知识，再比较两篇论文的方法，最后分析它们的局限').skill)
      .toMatchObject({ skillId: 'compose', steps: ['background', 'compare', 'critique'] });
    expect(resolveConversationIntent('解释核心概念，然后比较两篇论文').skill)
      .toMatchObject({ skillId: 'compose', steps: ['chat', 'compare'] });
    expect(startsNewCapability('compose')).toBe(true);
  });

  it('asks briefly for ambiguous or mixed interactive workflows before executing', () => {
    const vague = resolveConversationIntent('帮我分析一下');
    expect(vague.skill).toBeNull();
    expect(vague.clarification?.choices.map(choice => choice.skill.skillId)).toEqual(['chat', 'critique', 'compare', 'research']);
    const mixed = resolveConversationIntent('先精读这篇，再自测');
    expect(mixed.skill).toBeNull();
    expect(mixed.clarification?.choices.map(choice => choice.skill.skillId)).toEqual(['read', 'quiz']);
  });

  it('recognizes concise explanation before another requested capability', () => {
    expect(resolveConversationIntent('请先用一句话解释高斯数量和SH阶数的区别，再比较两篇论文').skill)
      .toMatchObject({ skillId: 'compose', steps: ['chat', 'compare'] });
    expect(resolveConversationIntent('先以两句话概括核心概念，然后批判这篇论文').skill)
      .toMatchObject({ skillId: 'compose', steps: ['chat', 'critique'] });
    expect(resolveConversationIntent('不要用一句话解释，再比较两篇论文').skill?.skillId).toBe('compare');
  });

  it('keeps explicit slash commands authoritative and ignores mentions and negated actions', () => {
    expect(resolveConversationIntent('/比较 解释核心概念，然后批判这些论文').skill?.skillId).toBe('compare');
    for (const input of ['比较是什么意思？', '这篇论文先比较算法，然后解释结果', '不要比较，然后也不要批判', '解释比较和批判这两个词的意思']) {
      expect(resolveConversationIntent(input).skill).toBeNull();
    }
    expect(resolveConversationIntent('比较两篇论文，但不要批判').skill?.skillId).toBe('compare');
  });
});
