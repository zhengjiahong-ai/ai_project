import React from 'react';
import MessageMarkdownRenderer from './MessageMarkdownRenderer';

const MarkdownContent = ({ children = '', className = '' }) => (
  <MessageMarkdownRenderer className={className}>{children}</MessageMarkdownRenderer>
);

export default MarkdownContent;
