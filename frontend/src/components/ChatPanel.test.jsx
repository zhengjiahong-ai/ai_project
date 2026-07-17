import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ChatPanel from './ChatPanel.tsx';

const defaultProps = {
  messages: [],
  onSendMessage: vi.fn(),
  onDeleteMessage: vi.fn(),
  onSaveToNote: vi.fn(),
  onCaptureArtifact: vi.fn(),
  onJumpToSource: vi.fn(),
  onAbortChat: vi.fn(),
  isLoading: false,
  contextTitle: 'Test Paper',
  contextSummary: 'A summary of the test paper.',
  nextActionHint: 'Try asking about methods.',
};

function renderChat(props = {}) {
  return render(<ChatPanel {...defaultProps} {...props} />);
}

describe('ChatPanel', () => {
  it('renders the panel header with context', () => {
    renderChat();
    expect(screen.getByText('延展问答')).toBeInTheDocument();
    expect(screen.getByText(/Test Paper/)).toBeInTheDocument();
    expect(screen.getByText(/A summary of the test paper/)).toBeInTheDocument();
    expect(screen.getByText(/Try asking about methods/)).toBeInTheDocument();
  });

  it('renders input textarea', () => {
    renderChat();
    const textarea = screen.getByPlaceholderText(/先问一个具体问题/);
    expect(textarea).toBeInTheDocument();
    expect(textarea).not.toBeDisabled();
  });

  it('disables input when loading', () => {
    renderChat({ isLoading: true });
    const textarea = screen.getByPlaceholderText(/Pixiu 正在回答中/);
    expect(textarea).toBeDisabled();
  });

  it('calls onSendMessage when typing and clicking send', () => {
    const onSend = vi.fn();
    renderChat({ onSendMessage: onSend });

    const textarea = screen.getByPlaceholderText(/先问一个具体问题/);
    fireEvent.change(textarea, { target: { value: '这篇论文的核心贡献？' } });

    const sendButton = textarea.parentElement.querySelector('button:last-child');
    fireEvent.click(sendButton);

    expect(onSend).toHaveBeenCalledWith('这篇论文的核心贡献？');
  });

  it('sends message on Enter key', () => {
    const onSend = vi.fn();
    renderChat({ onSendMessage: onSend });

    const textarea = screen.getByPlaceholderText(/先问一个具体问题/);
    fireEvent.change(textarea, { target: { value: 'Hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(onSend).toHaveBeenCalledWith('Hello');
  });

  it('does not send on Shift+Enter', () => {
    const onSend = vi.fn();
    renderChat({ onSendMessage: onSend });

    const textarea = screen.getByPlaceholderText(/先问一个具体问题/);
    fireEvent.change(textarea, { target: { value: 'multiline' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it('renders user and AI messages', () => {
    const messages = [
      { id: 1, role: 'user', content: '什么是注意力机制？' },
      { id: 2, role: 'ai', content: '注意力机制是神经网络中...' },
    ];
    renderChat({ messages });

    expect(screen.getByText('什么是注意力机制？')).toBeInTheDocument();
    // AI messages are rendered inside InsightCard with markdown
    expect(screen.getByText(/注意力机制是神经网络中/)).toBeInTheDocument();
  });

  it('renders loading skeleton when isLoading', () => {
    renderChat({
      isLoading: true,
      messages: [{ id: 1, role: 'user', content: 'Hi' }],
    });
    expect(screen.getByText('Pixiu 正在整理回答')).toBeInTheDocument();
    // The loading indicator shows a pulsing progress bar
    expect(screen.getByText(/先给一句结论/)).toBeInTheDocument();
  });

  it('calls onAbortChat when stop button is clicked', () => {
    const onAbort = vi.fn();
    renderChat({ isLoading: true, onAbortChat: onAbort });

    const stopButton = screen.getByTitle('停止生成');
    fireEvent.click(stopButton);
    expect(onAbort).toHaveBeenCalled();
  });

  it('disables send button when input is empty', () => {
    renderChat();
    const textarea = screen.getByPlaceholderText(/先问一个具体问题/);
    const sendButton = textarea.parentElement.querySelector('button:last-child');
    expect(sendButton).toBeDisabled();
  });

  it('quick tag buttons populate input', () => {
    renderChat();
    const tagButton = screen.getByText('# 核心结论');
    fireEvent.click(tagButton);

    const textarea = screen.getByPlaceholderText(/先问一个具体问题/);
    expect(textarea.value).toBe('# 核心结论');
  });

  it('calls onDeleteMessage on message delete', () => {
    const onDelete = vi.fn();
    const messages = [{ id: 1, role: 'ai', content: '回答内容' }];
    const originalConfirm = window.confirm;
    window.confirm = vi.fn(() => true);

    renderChat({ messages, onDeleteMessage: onDelete });

    // Multiple delete buttons exist (left + right of message), pick the first
    const deleteButtons = screen.getAllByTitle('删除此消息');
    fireEvent.click(deleteButtons[0]);

    expect(window.confirm).toHaveBeenCalled();
    expect(onDelete).toHaveBeenCalledWith(0);

    window.confirm = originalConfirm;
  });
});
