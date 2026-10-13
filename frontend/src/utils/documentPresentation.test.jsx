import { describe, expect, it } from 'vitest';
import { documentDisplayTitle, questionTopic } from './documentPresentation';
import { documentPreview, taskDocumentNavigation } from './taskDocumentNavigation';

describe('document names and identities', () => {
  it('keeps research citation targets out of navigation previews without modifying the saved report', () => {
    const report = { text: '编码特征。[[1]](#research-evidence-e1) 解码形变。[2](#research-evidence-e2) [论文](https://arxiv.org/abs/2310.08528)' };
    expect(documentPreview(report)).toBe('编码特征。 解码形变。 论文');
    expect(report.text).toContain('[[1]](#research-evidence-e1)');
  });
  it('makes same-title records distinguishable without mutating their content or merging identities', () => {
    const task = { notes: [{ id: 'a', title: '实验', text: '## 方案\n**控制高斯数量**，测量质量。[1]', createdAt: '2026-10-12T01:00:00Z' },
      { id: 'b', title: '实验', text: '固定 SH 阶数，测量速度。', createdAt: '2026-10-12T02:00:00Z' }] };
    const before = JSON.stringify(task);
    const rows = taskDocumentNavigation(task);
    expect(rows.map(row => row.item.id)).toEqual(['b', 'a']);
    expect(rows.map(row => row.preview)).toEqual(['固定 SH 阶数，测量速度。', '控制高斯数量，测量质量。']);
    expect(rows.every(row => row.date)).toBe(true);
    expect(documentPreview({ text: '' })).toBe('');
    expect(JSON.stringify(task)).toBe(before);
  });
  const papers = [{ id: 'light', title: 'LightGaussian: Unbounded Compression' }];
  it('derives different generic result names from their retained original questions without changing records', () => {
    const first = { id: 'one', title: '对话成果', capability: 'critique', paperIds: ['light'], critique: { question: { original: '/批判 帮我核对画质保持的条件？' } } };
    const second = { id: 'two', title: '对话成果', capability: 'research', question: '/研究 剪枝与 SH 降阶的消融实验方案' };
    const task = { artifacts: [first, second], messages: [], notes: [] };
    const before = JSON.stringify(task);
    expect(taskDocumentNavigation(task, papers).map(entry => entry.title)).toEqual(['LightGaussian：核对画质保持的条件', '剪枝与 SH 降阶的消融实验方案']);
    expect(JSON.stringify(task)).toBe(before);
  });
  it('preserves user names even when they look generic and falls back honestly when no question was retained', () => {
    expect(documentDisplayTitle({ title: '对话成果', titleOrigin: 'user' }, {}, papers)).toBe('对话成果');
    expect(documentDisplayTitle({ title: '对话成果', capability: 'critique', paperIds: ['light'], text: '质量始终没有损失。' }, {}, papers)).toBe('LightGaussian · 批判阅读');
  });
  it('uses the original question of the saved message instead of a later unrelated question', () => {
    const item = { id: 'result', title: '对话成果', sourceMessageId: 'reply' };
    const task = { messages: [{ id: 'question', role: 'user', content: '/比较 请比较压缩与质量的取舍' },
      { id: 'reply', role: 'ai', content: '回答' }, { id: 'later', role: 'user', content: '另一个问题' }] };
    expect(documentDisplayTitle(item, task)).toBe('比较压缩与质量的取舍');
  });
  it('removes command and material syntax but preserves the question rather than inventing a conclusion', () => {
    expect(questionTopic('/批判 @{LightGaussian} 请画质几乎不变可信吗？')).toBe('画质几乎不变可信吗');
  });
});
