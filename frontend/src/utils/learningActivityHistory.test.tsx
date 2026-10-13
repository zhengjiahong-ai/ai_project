import { describe, expect, it } from 'vitest';
import { learningActivityHistory } from './learningActivityHistory';

describe('saved learning activity navigation', () => {
  it('does not present revisions of the current lesson as separate lessons', () => {
    const task = { activityHistory:[{ activityId:'a', revision:0 },{ activityId:'a', revision:1 }],
      activeActivity:{ activityId:'a', revision:2, status:'active' } };
    expect(learningActivityHistory(task)).toEqual([]);
    expect(task.activityHistory).toHaveLength(2);
  });
  it('shows the final authoritative record and one latest snapshot of older activities', () => {
    const final = { activityId:'a', revision:3, status:'finished' };
    expect(learningActivityHistory({ activeActivity:final, activityHistory:[
      { activityId:'b', revision:2 }, { activityId:'b', revision:1 }, { activityId:'a', revision:2 },
    ] })).toEqual([{ activityId:'b', revision:2 }, final]);
  });
  it('keeps unrelated legacy records without identifiers', () => {
    expect(learningActivityHistory({ activityHistory:[{ status:'finished' },{ status:'paused' }] })).toHaveLength(2);
  });
});
