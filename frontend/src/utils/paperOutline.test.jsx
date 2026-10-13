import { describe, expect, it } from 'vitest';
import { buildPaperOutlineModel } from './appHelpers';

describe('paper navigation outline', () => {
  it('excludes table rows, formula fragments and fake numeric sections while preserving genuine sections', () => {
    const titles = ['Abstract', '3 Methods', '3.2 Gaussian Pruning & Recovery', '4 Experiments',
      '0 Section 0', '173 Section 173', '4 Vnorm = min', 'Ours (93 fps)',
      '0.14 8.6MB 22.22 0.759 0.257 VQ-DVGO [49] 4.65 63MB 24.23 0.636 0.393',
      '3 with negligible quality degradation while preserving rendering',
      'Algorithm 1 The overall pipeline of LightGaussian', '6 More Experiment Results'];
    const model = buildPaperOutlineModel({ paper_structure: { sections: titles.map((title, i) => ({ id: String(i), title, pageIndex: i })) } });
    expect(model.items.map(item => item.label)).toEqual(titles.slice(0, 4).concat(titles.slice(-2)));
    expect(model.items[2].pageIndex).toBe(2);
    expect(model.items[2].parentId).toBe('1');
  });
});
