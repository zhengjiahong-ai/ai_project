const PROTECTED_SEGMENT_PATTERN = /(```[\s\S]*?```|`[^`\n]*`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)/g;
const PROTECTED_SEGMENT_FULL_PATTERN = /^(?:```[\s\S]*```|`[^`\n]*`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)$/;
const MATH_COMMAND_PATTERN =
  /\\(?:sum|frac|prod|int|sqrt|alpha|beta|gamma|delta|theta|lambda|mu|sigma|pi|cdot|times|leq|geq|neq|approx|left|right|mathbb|mathbf|mathrm|operatorname|ell)\b/;
const SUBSCRIPT_PATTERN = /[A-Za-z][A-Za-z0-9]*_\{?[^}\s]+\}?/;
const SUPERSCRIPT_PATTERN = /[A-Za-z][A-Za-z0-9]*\^\{?[^}\s]+\}?/;
const SUB_OR_SUP_PATTERN = /(?:[A-Za-z][A-Za-z0-9]*|[|][A-Za-z][A-Za-z0-9|]*[|])(?:_\{?[^}\s]+\}?|\^\{?[^}\s]+\}?)+/;
const CJK_PATTERN = /[\u3400-\u9fff]/g;
const INLINE_MATH_BOUNDARY_PATTERN = /(^|[\s(:,])(\|?[A-Za-z][A-Za-z0-9|]*(?:_\{?[^}\s]+\}?|\^\{?[^}\s]+\}?)+\|?)(?=$|[\s).,;:])/gm;

const applyToUnprotectedSlices = (text, transformer) =>
  text
    .split(PROTECTED_SEGMENT_PATTERN)
    .map((segment) => (PROTECTED_SEGMENT_FULL_PATTERN.test(segment) ? segment : transformer(segment)))
    .join('');

const countMatches = (pattern, value) => (value.match(pattern) || []).length;

const normalizeLatexDelimiters = (text) =>
  text
    .replace(/\\\[((?:.|\n)*?)\\\]/g, (_, content) => `$$\n${content.trim()}\n$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, content) => `$${content.trim()}$`);

const isLikelyMathExpression = (candidate) => {
  const text = String(candidate || '').trim();
  if (!text || text.length < 3 || text.length > 180) {
    return false;
  }

  if (MATH_COMMAND_PATTERN.test(text)) {
    return true;
  }

  const cjkCount = countMatches(CJK_PATTERN, text);
  if (cjkCount > 6) {
    return false;
  }

  if (SUB_OR_SUP_PATTERN.test(text)) {
    return true;
  }

  const hasAssignment = text.includes('=');
  const hasSubscript = SUBSCRIPT_PATTERN.test(text);
  const hasSuperscript = SUPERSCRIPT_PATTERN.test(text);
  const hasIndexedBounds = /[_^]\{[^}]+\}/.test(text);
  const hasMathBars = /\|[A-Za-z][A-Za-z0-9_^{|}]*\|/.test(text);

  return hasAssignment && (hasSubscript || hasSuperscript || hasIndexedBounds || hasMathBars);
};

const wrapInlineMath = (candidate) => `$${candidate.trim()}$`;
const wrapDisplayMath = (candidate) => `$$\n${candidate.trim()}\n$$`;

const wrapParenthesizedExpressions = (text) =>
  text
    .split('\n')
    .map((line) => {
      const spans = [];
      const stack = [];

      for (let index = 0; index < line.length; index += 1) {
        const char = line[index];
        if (char === '(' || char === '\uff08') {
          stack.push({ index, char });
          continue;
        }

        const top = stack.at(-1);
        if (!top) {
          continue;
        }

        const isClosingParenthesis =
          (top.char === '(' && char === ')') ||
          (top.char === '\uff08' && char === '\uff09');

        if (!isClosingParenthesis) {
          continue;
        }

        stack.pop();
        const candidate = line.slice(top.index, index + 1);
        const inner = candidate.slice(1, -1).trim();
        if (isLikelyMathExpression(inner) && countMatches(CJK_PATTERN, inner) === 0) {
          spans.push({ start: top.index, end: index + 1, text: candidate });
        }
      }

      if (spans.length === 0) {
        return line;
      }

      const selectedSpans = [];
      for (const span of spans.sort((left, right) => (right.end - right.start) - (left.end - left.start))) {
        const overlapsExisting = selectedSpans.some(
          (selected) => span.start < selected.end && span.end > selected.start,
        );
        if (!overlapsExisting) {
          selectedSpans.push(span);
        }
      }

      let rebuilt = '';
      let cursor = 0;
      for (const span of selectedSpans.sort((left, right) => left.start - right.start)) {
        rebuilt += line.slice(cursor, span.start);
        rebuilt += wrapInlineMath(span.text);
        cursor = span.end;
      }

      rebuilt += line.slice(cursor);
      return rebuilt;
    })
    .join('\n');

const wrapPureFormulaLines = (text) =>
  text
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#') || trimmed.startsWith('-') || trimmed.startsWith('*')) {
        return line;
      }

      if (countMatches(CJK_PATTERN, trimmed) > 0 || !isLikelyMathExpression(trimmed)) {
        return line;
      }

      return wrapDisplayMath(trimmed);
    })
    .join('\n');

const replaceWrappedCandidate = (candidate) => {
  const normalizedCandidate = candidate.trim();
  if (countMatches(CJK_PATTERN, normalizedCandidate) > 0) {
    return candidate;
  }

  return isLikelyMathExpression(normalizedCandidate) ? wrapInlineMath(normalizedCandidate) : candidate;
};

const wrapCommandExpressions = (text) =>
  text.replace(
    /(^|[\s:,\u3001\u3002\uff0c\uff1a])((?:\\(?:sum|frac|prod|int|sqrt|alpha|beta|gamma|delta|theta|lambda|mu|sigma|pi|cdot|times|leq|geq|neq|approx|left|right|mathbb|mathbf|mathrm|operatorname|ell)[^`$\u3400-\u9fff\u3001\u3002\uff0c\uff1a,;:\n]*)+)/gm,
    (match, prefix, candidate) => `${prefix}${replaceWrappedCandidate(candidate.trim())}`,
  );

const wrapAssignmentExpressions = (text) =>
  text.replace(
    /(^|[\s:,\u3001\u3002\uff0c\uff1a])([A-Za-z|][A-Za-z0-9|{}^_]*(?:\s*=\s*[^,\u3001\u3002\uff0c\uff1a;:\u3400-\u9fff\n]{1,160}))/gm,
    (match, prefix, candidate) => `${prefix}${replaceWrappedCandidate(candidate.trim())}`,
  );

const wrapInlineIndexedTokens = (text) =>
  text.replace(INLINE_MATH_BOUNDARY_PATTERN, (match, prefix, candidate) => `${prefix}${wrapInlineMath(candidate.trim())}`);

export const preprocessMathMarkdown = (content = '') => {
  const text = typeof content === 'string' ? content : String(content ?? '');

  let output = normalizeLatexDelimiters(text);
  output = applyToUnprotectedSlices(output, wrapParenthesizedExpressions);
  output = applyToUnprotectedSlices(output, wrapPureFormulaLines);
  output = applyToUnprotectedSlices(output, wrapCommandExpressions);
  output = applyToUnprotectedSlices(output, wrapAssignmentExpressions);
  output = applyToUnprotectedSlices(output, wrapInlineIndexedTokens);
  return output;
};
