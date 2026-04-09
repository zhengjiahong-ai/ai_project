import React from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkMath from 'remark-math';
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

const MessageMarkdownRenderer = ({ children = '', className = '' }) => {
  const normalizedContent = preprocessMathMarkdown(children);

  return React.createElement(
    'div',
    { className: `markdown-content ${className}`.trim() },
    React.createElement(
      ReactMarkdown,
      {
        remarkPlugins: [remarkMath],
        rehypePlugins: [[rehypeKatex, rehypeKatexOptions]],
      },
      normalizedContent,
    ),
  );
};

export default MessageMarkdownRenderer;
