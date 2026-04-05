import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkMath from 'remark-math';
import { preprocessMathMarkdown } from '../utils/mathMarkdown.js';
import { buildExplainSelectionPayload, normalizePdfSelectionText } from '../utils/pdfFormulaSelection.js';

const rehypeKatexOptions = {
  output: 'html',
  strict: 'ignore',
  throwOnError: false,
};

const renderMarkdown = (content) =>
  renderToStaticMarkup(
    React.createElement(
      ReactMarkdown,
      {
        remarkPlugins: [remarkMath],
        rehypePlugins: [[rehypeKatex, rehypeKatexOptions]],
      },
      content,
    ),
  );

const run = async () => {
  const plainSource = 'Plain **Markdown** content';
  const plainMarkup = renderMarkdown(preprocessMathMarkdown(plainSource));
  assert.match(plainMarkup, /<strong>Markdown<\/strong>/);
  assert.equal(preprocessMathMarkdown(plainSource), plainSource);

  const inlineMathSource = 'Loss is $L = \\\\sum_i x_i$';
  const inlineMathMarkup = renderMarkdown(preprocessMathMarkdown(inlineMathSource));
  assert.match(inlineMathMarkup, /katex/);
  assert.equal(preprocessMathMarkdown(inlineMathSource), inlineMathSource);

  const blockMathMarkup = renderMarkdown(preprocessMathMarkdown('\n$$\nE = mc^2\n$$\n'));
  assert.match(blockMathMarkup, /katex-display/);

  const indexedTokenMarkup = renderMarkdown(preprocessMathMarkdown('Token x_t^i should render as math.'));
  assert.match(indexedTokenMarkup, /katex/);

  const commandMarkup = renderMarkdown(
    preprocessMathMarkdown('Use \\\\sum_{i=1}^n x_i together with \\\\frac{1}{N}.'),
  );
  assert.match(commandMarkup, /katex/);

  const parenthesizedMarkup = renderMarkdown(
    preprocessMathMarkdown('Formula (T_t = {(x_t^i, y_t^i)}_{i=1}^{|T_t|}) should render inline.'),
  );
  assert.match(parenthesizedMarkup, /katex/);

  const latexDelimiterMarkup = renderMarkdown(
    preprocessMathMarkdown('Use \\(x_t^i\\) and then display \\[E = mc^2\\].'),
  );
  assert.match(latexDelimiterMarkup, /katex/);

  const normalizedSelection = normalizePdfSelectionText('T t ={(x t i, y t i)} [T t| i =1');
  assert.equal(normalizedSelection.normalizedText, 'T_t={(x_t^i, y_t^i)}_{i=1}^{|T_t|}');
  assert.equal(normalizedSelection.displayText, '$T_t={(x_t^i, y_t^i)}_{i=1}^{|T_t|}$');

  const selectionPayload = buildExplainSelectionPayload('T t ={(x t i, y t i)} [T t| i =1');
  assert.match(selectionPayload.displayMessage, /\$T_t=\{\(x_t\^i, y_t\^i\)\}_\{i=1\}\^\{\|T_t\|\}\$/);
  assert.match(selectionPayload.backendPrompt, /Markdown LaTeX/);

  console.log('markdown math rendering smoke tests passed');
};

run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
