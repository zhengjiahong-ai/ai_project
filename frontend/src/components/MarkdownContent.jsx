import React from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkMath from 'remark-math';
import { preprocessMathMarkdown } from '../utils/mathMarkdown';

const rehypeKatexOptions = {
  output: 'html',
  strict: 'ignore',
  throwOnError: false,
};

const MarkdownContent = ({ children = '', className = '' }) => {
  const normalizedContent = preprocessMathMarkdown(children);

  return (
    <div className={`markdown-content ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, rehypeKatexOptions]]}>
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownContent;
