import React from 'react';
import MessageMarkdownRenderer from './MessageMarkdownRenderer';

const MarkdownContent = ({ children = '', className = '', components = {} }) => (
  <MessageMarkdownRenderer className={className} components={components}>{children}</MessageMarkdownRenderer>
);

export default MarkdownContent;
