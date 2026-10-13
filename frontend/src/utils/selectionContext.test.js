import assert from 'node:assert/strict';
import { focusSelectionContext } from './selectionContext.js';

const page = 'Earlier unrelated paragraph. '.repeat(200) + 'Global Significance Calculation. ' +
  'The score includes opacity, transmittance T, and adjusted volume. '.repeat(10) + 'Later section. '.repeat(200);
const context = focusSelectionContext(page, 'Significance', 2800);
assert.ok(context.includes('Global Significance Calculation.'));
assert.ok(context.includes('transmittance T'));
assert.ok(context.length <= 2800);
assert.ok(focusSelectionContext(page, 'SIGNIFICANCE', 2800).includes('transmittance T'));
assert.ok(focusSelectionContext(page.replace('Global Significance Calculation.', 'Global\n  Significance\tCalculation.'),
  'Global Significance Calculation.', 2800).includes('transmittance T'));
assert.equal(focusSelectionContext('Short paragraph.', 'paragraph'), 'Short paragraph.');
assert.equal(focusSelectionContext('a'.repeat(5000), 'not found', 1000), 'a'.repeat(1000));
console.log('selection context tests passed');
