import React from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import { preprocessMathMarkdown } from '../utils/mathMarkdown.js';

export const rehypeKatexOptions = {
  output: 'html',
  strict: 'ignore',
  throwOnError: false,
};

export const getMessageMarkdownClassName = (role = 'ai', surface = 'chat') => {
  const classes = [];

  if (role === 'user') {
    classes.push('chat-message-user');
    if (surface === 'chat') {
      classes.push('text-white');
    }
  } else {
    classes.push('chat-message-ai', 'prose', 'prose-sm', 'prose-slate', 'max-w-none');
  }

  if (surface === 'popup') {
    classes.push('chat-message-popup');
  }

  return classes.join(' ');
};

const outsideCodeFence = (text) => {
  let fence = null;
  for (const line of text.split('\n')) {
    const match = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (!match) continue;
    if (!fence) fence = match[1];
    else if (match[1][0] === fence[0] && match[1].length >= fence.length) fence = null;
  }
  return !fence;
};

// Render only this narrow, generated folding syntax as native React elements.
// General HTML remains escaped by react-markdown.
export const splitFoldedMarkdown = (text) => {
  const parts = [];
  const pattern = /^<details>[ \t]*\r?\n<summary>([^<\n]*)<\/summary>[ \t]*\r?\n([\s\S]*?)^<\/details>[ \t]*$/gm;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (!outsideCodeFence(text.slice(0, match.index))) continue;
    if (match.index > cursor) parts.push({ text: text.slice(cursor, match.index) });
    parts.push({ summary: match[1], text: match[2] });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length || !parts.length) parts.push({ text: text.slice(cursor) });
  return parts;
};

const MessageMarkdownRenderer = ({ children = '', className = '', components = {} }) => {
  const normalizedContent = preprocessMathMarkdown(children);
  const markdown = (text, key) => React.createElement(ReactMarkdown, {
    key,
    remarkPlugins: [remarkMath, remarkGfm],
    rehypePlugins: [[rehypeKatex, rehypeKatexOptions]],
    components: {
      table: ({ children: tableChildren }) => React.createElement('div', { className: 'my-3 overflow-x-auto rounded-lg border border-slate-200' },
        React.createElement('table', { className: 'min-w-[640px] w-full border-collapse text-left text-sm' }, tableChildren)),
      th: ({ children: cellChildren }) => React.createElement('th', { className: 'border-b border-slate-200 p-3 align-top font-semibold' }, cellChildren),
      td: ({ children: cellChildren }) => React.createElement('td', { className: 'border-b border-slate-200 p-3 align-top leading-relaxed' }, cellChildren),
      ...components,
    },
  }, text);
  return React.createElement(
    'div',
    { className: `markdown-content ${className}`.trim() },
    ...splitFoldedMarkdown(normalizedContent).map((part, index) => part.summary !== undefined
      ? React.createElement('details', { key: index, className: 'my-3 rounded-lg border border-slate-200 p-3' },
        React.createElement('summary', { className: 'cursor-pointer text-sm font-medium' }, part.summary),
        markdown(part.text, 'content'))
      : markdown(part.text, index)),
  );
};

export default MessageMarkdownRenderer;
