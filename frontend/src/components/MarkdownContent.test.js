import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkMath from 'remark-math';
import { preprocessMathMarkdown } from '../utils/mathMarkdown.js';
import { buildExplainSelectionPayload, normalizePdfSelectionText } from '../utils/pdfFormulaSelection.js';
import MessageMarkdownRenderer, { getMessageMarkdownClassName } from './MessageMarkdownRenderer.js';

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

  const sentenceWithFormulaToken = preprocessMathMarkdown(
    'T_t and T_t^i are available data (non-i.i.d.) in another client.',
  );
  assert.equal(sentenceWithFormulaToken, '$T_t$ and $T_t^i$ are available data (non-i.i.d.) in another client.');

  const latexDelimiterMarkup = renderMarkdown(
    preprocessMathMarkdown('Use \\(x_t^i\\) and then display \\[E = mc^2\\].'),
  );
  assert.match(latexDelimiterMarkup, /katex/);

  const mixedSentenceMarkup = renderMarkdown(
    preprocessMathMarkdown('The set {(x_t^i, y_t^i)}_{i=1}^{|T_t|} contains all sample pairs.'),
  );
  assert.match(mixedSentenceMarkup, /katex/);
  assert.doesNotMatch(mixedSentenceMarkup, /\$\$\$/);

  const normalizedSelection = normalizePdfSelectionText('T t ={(x t i, y t i)} [T t| i =1');
  assert.equal(normalizedSelection.normalizedText, 'T_t={(x_t^i, y_t^i)}_{i=1}^{|T_t|}');
  assert.equal(
    normalizedSelection.displayText,
    '$$\nT_t={\\left\\{(x_t^i, y_t^i)\\right\\}}_{i=1}^{\\lvert T_t \\rvert}\n$$',
  );

  const partialSelection = normalizePdfSelectionText('(x t i, y t i)}|T t|i=1,');
  assert.equal(partialSelection.normalizedText, '{(x_t^i, y_t^i)}_{i=1}^{|T_t|}');
  assert.equal(
    partialSelection.displayText,
    '$$\n{\\left\\{(x_t^i, y_t^i)\\right\\}}_{i=1}^{\\lvert T_t \\rvert}\n$$',
  );

  const englishSentenceSelection = normalizePdfSelectionText(
    'T_t and T_t^i are available data (non-i.i.d.) in another client',
  );
  assert.equal(englishSentenceSelection.isFormulaLike, false);

  const selectionPayload = buildExplainSelectionPayload('T t ={(x t i, y t i)} [T t| i =1');
  assert.equal(
    selectionPayload.displayMessage,
    '$$\nT_t={\\left\\{(x_t^i, y_t^i)\\right\\}}_{i=1}^{\\lvert T_t \\rvert}\n$$',
  );
  assert.match(selectionPayload.backendPrompt, /不要描述公式恢复或归一化过程/);
  assert.doesNotMatch(selectionPayload.backendPrompt, /归一化后的选区|恢复后的公式如下|根据你提供的原始选区内容|可以将其恢复为/);

  const displayMarkup = renderMarkdown(preprocessMathMarkdown(selectionPayload.displayMessage));
  assert.match(displayMarkup, /katex-display/);
  assert.match(displayMarkup, /katex/);
  assert.doesNotMatch(displayMarkup, /T_t=\{\(x_t\^i, y_t\^i\)\}_\{i=1\}\^\{\|T_t\|\}/);

  const plainSelectionPayload = buildExplainSelectionPayload('The optimization objective');
  assert.equal(plainSelectionPayload.displayMessage, 'The optimization objective');
  assert.match(plainSelectionPayload.backendPrompt, /请直接解释下面这段内容/);

  assert.equal(getMessageMarkdownClassName('user', 'chat'), 'chat-message-user text-white');
  assert.equal(getMessageMarkdownClassName('user', 'popup'), 'chat-message-user chat-message-popup');

  const chatMessageMarkup = renderToStaticMarkup(
    React.createElement(
      MessageMarkdownRenderer,
      { className: getMessageMarkdownClassName('user', 'chat') },
      selectionPayload.displayMessage,
    ),
  );
  assert.match(chatMessageMarkup, /chat-message-user text-white/);
  assert.match(chatMessageMarkup, /katex/);

  const popupMessageMarkup = renderToStaticMarkup(
    React.createElement(
      MessageMarkdownRenderer,
      { className: getMessageMarkdownClassName('user', 'popup') },
      selectionPayload.displayMessage,
    ),
  );
  assert.match(popupMessageMarkup, /chat-message-popup/);
  assert.match(popupMessageMarkup, /katex/);

  console.log('markdown math rendering smoke tests passed');
};

run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
