import assert from 'node:assert/strict';

import {
  getParseStatusLabel,
  getParseWarningMessage,
  normalizeParseStatus,
} from './parseStatusModel.js';

assert.equal(normalizeParseStatus({ parseStatus: 'scanned_or_low_text', ragIndexed: false }), 'scanned_or_low_text');
assert.equal(getParseStatusLabel({ parseStatus: 'scanned_or_low_text', ragIndexed: false }), '需 OCR');
assert.equal(normalizeParseStatus({ parseStatus: 'parsed', ragIndexed: false }), 'index_error');
assert.equal(getParseStatusLabel({ parseStatus: 'parsed', ragIndexed: true }), '已解析');
assert.equal(getParseStatusLabel({ parseStatus: '索引异常' }), '索引异常');
assert.equal(getParseStatusLabel({ parseStatus: '已解析' }), '已解析');
assert.match(
  getParseWarningMessage({ parseStatus: 'scanned_or_low_text' }),
  /OCR|文字版 PDF/,
);
assert.equal(getParseWarningMessage({ parseStatus: 'parsed', ragIndexed: true }), null);

console.log('parse status model tests passed');
