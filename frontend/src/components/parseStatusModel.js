export const PARSE_STATUS_PARSED = 'parsed';
export const PARSE_STATUS_SCANNED_OR_LOW_TEXT = 'scanned_or_low_text';
export const PARSE_STATUS_INDEX_ERROR = 'index_error';

export const DEFAULT_LOW_TEXT_WARNING =
  '检测到的 PDF 文本量过低，可能是扫描件。请先执行 OCR 或更换文字版 PDF；问答、分析和检索能力可能受限。';

export const normalizeParseStatus = (paper = {}) => {
  const status = paper?.parseStatus;
  if (status === PARSE_STATUS_SCANNED_OR_LOW_TEXT || status === '需 OCR') {
    return PARSE_STATUS_SCANNED_OR_LOW_TEXT;
  }
  if (status === PARSE_STATUS_INDEX_ERROR || status === '索引异常') {
    return PARSE_STATUS_INDEX_ERROR;
  }
  if (paper?.ragIndexed === false) {
    return PARSE_STATUS_INDEX_ERROR;
  }
  return PARSE_STATUS_PARSED;
};

export const getParseStatusLabel = (paper = {}) => {
  const status = normalizeParseStatus(paper);
  if (status === PARSE_STATUS_SCANNED_OR_LOW_TEXT) return '需 OCR';
  if (status === PARSE_STATUS_INDEX_ERROR) return '索引异常';
  return '已解析';
};

export const getParseWarningMessage = (paper = {}) =>
  normalizeParseStatus(paper) === PARSE_STATUS_SCANNED_OR_LOW_TEXT
    ? paper?.parseMessage || DEFAULT_LOW_TEXT_WARNING
    : null;
