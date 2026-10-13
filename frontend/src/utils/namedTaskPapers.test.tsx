import { describe, expect, it } from 'vitest';
import { resolveNamedTaskPapers } from './namedTaskPapers';

const papers = [{ id: 'a', title: '论文甲的方法' }, { id: 'b', title: '论文乙的实验' }, { id: 'c', title: '任务外论文' }];
describe('named task materials', () => {
  it('resolves one or multiple names independently of the reading focus', () => {
    expect(resolveNamedTaskPapers('只根据《论文乙的实验》回答', papers, ['a', 'b'])).toEqual(['b']);
    expect(resolveNamedTaskPapers('比较 @{b} 和 @{a}', papers, ['a', 'b'])).toEqual(['b', 'a']);
    expect(resolveNamedTaskPapers('论文乙的实验 的方法是什么', papers, ['a', 'b'])).toEqual(['b']);
  });
  it('rejects unknown explicit names, ambiguous names, and outside-task papers', () => {
    expect(() => resolveNamedTaskPapers('《不存在》', papers, ['a'])).toThrow('找不到');
    expect(() => resolveNamedTaskPapers('@{c}', papers, ['a'])).toThrow('不属于');
    expect(() => resolveNamedTaskPapers('《同名》', [{ id: 'a', title: '同名' }, { id: 'b', title: '同名' }], ['a', 'b'])).toThrow('同名');
  });
  it('leaves ordinary deictic questions to task context resolution', () => {
    expect(resolveNamedTaskPapers('这篇的方法是什么', papers, ['a', 'b'])).toBeUndefined();
  });
  it('resolves bare @ names and keeps IDs unambiguous when another title matches the ID', () => {
    expect(resolveNamedTaskPapers('只根据 @论文乙的实验 回答', papers, ['a', 'b'])).toEqual(['b']);
    expect(() => resolveNamedTaskPapers('只根据 @不存在 回答', papers, ['a', 'b'])).toThrow('找不到');
    expect(resolveNamedTaskPapers('@{a}', [{ id: 'a', title: '甲' }, { id: 'b', title: 'a' }], ['a', 'b'])).toEqual(['a']);
  });
});
