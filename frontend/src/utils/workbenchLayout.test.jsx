import { describe, it, expect } from 'vitest';
import { DEFAULT_WORKBENCH_LAYOUT, workbenchLayout } from './workbenchLayout';

describe('temporary workbench adaptation', () => {
  it('preserves preferences while closing navigation and clamping both pane widths', () => {
    const preference = { ...DEFAULT_WORKBENCH_LAYOUT, readerPercent: 72 };
    const before = JSON.stringify(preference);
    for (const width of [1440, 1280, 1100]) {
      const view = workbenchLayout(preference, width);
      expect(view.available * view.readerPercent / 100).toBeGreaterThanOrEqual(479.99);
      expect(view.available * (100 - view.readerPercent) / 100).toBeGreaterThanOrEqual(339.99);
    }
    expect(workbenchLayout(preference, 1280).drawer).toBe(true);
    expect(workbenchLayout(preference, 1440).navigation).toBe(true);
    expect(JSON.stringify(preference)).toBe(before);
  });
  it('allows pinned navigation only when the panes can still fit', () => {
    const preference = { ...DEFAULT_WORKBENCH_LAYOUT, navPinnedMedium: true, navWidth: 320 };
    expect(workbenchLayout(preference, 1280).navigation).toBe(true);
    expect(workbenchLayout(preference, 1100).drawer).toBe(true);
    const tight = workbenchLayout(preference, 1152);
    expect(tight.minPercent).toBeLessThanOrEqual(tight.maxPercent);
    expect(tight.available * tight.readerPercent / 100).toBeGreaterThanOrEqual(479.99);
    expect(workbenchLayout(preference, 900).compact).toBe(true);
    expect(workbenchLayout(preference, 390).compact).toBe(true);
  });
});
