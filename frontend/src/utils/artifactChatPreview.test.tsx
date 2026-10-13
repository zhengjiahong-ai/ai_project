import { describe, expect, it } from 'vitest';
import { artifactChatPreview } from './artifactChatPreview';

describe('stored artifact chat preview', () => {
  it('keeps prose conclusions and leaves comparison tables in the artifact', () => {
    const stored = '## 比较结果\n\nA 最大化感知 SINR，B 最大化雷达 MI。\n\n| 论文 | 目标 |\n|---|---|\n| A | SINR |';
    expect(artifactChatPreview(stored)).toBe('A 最大化感知 SINR，B 最大化雷达 MI。');
    expect(stored).toContain('| A | SINR |');
  });
  it('does not cut a long formula or a table row to create a preview', () => {
    expect(artifactChatPreview('| A | ' + 'x'.repeat(1000) + ' |')).toBe('完整结果已保存在成果中。');
    expect(artifactChatPreview('短结论。' + 'x'.repeat(1000))).toBe('短结论。');
  });
  it('preserves a short ordinary result', () => {
    expect(artifactChatPreview('原文结论。')).toBe('原文结论。');
  });
});
