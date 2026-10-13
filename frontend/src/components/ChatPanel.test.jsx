import React from 'react';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
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
};

function renderChat(props = {}) {
  return render(<ChatPanel {...defaultProps} {...props} />);
}

describe('ChatPanel', () => {
  it('selects notes as research context without adding them as paper evidence', () => {
    const choose = vi.fn();
    renderChat({ enableSkills: true, researchCapabilities: { enabled: true },
      researchContextOptions: [{ id: 'note:n', title: '我的实验设想' }], onResearchContextRefsChange: choose });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '/研究 核查实验设想' } });
    fireEvent.click(screen.getByRole('button', { name: '对话材料' }));
    fireEvent.click(screen.getByText('参考笔记与成果'));
    fireEvent.click(screen.getByRole('checkbox', { name: '我的实验设想' }));
    expect(choose).toHaveBeenCalledWith(['note:n']);
    expect(screen.getByText(/论文事实仍回查原文/)).toBeInTheDocument();
  });
  beforeAll(() => {
    // jsdom does not implement the native dialog top layer; real focus trapping is checked in-browser.
    if (!HTMLDialogElement.prototype.showModal) HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    if (!HTMLDialogElement.prototype.close) HTMLDialogElement.prototype.close = function () { this.open = false; };
  });
  beforeEach(() => localStorage.clear());
  it('restores selected chips separately from prose and submits the restored scope after editing', async () => {
    const materials = [{ id: 'a', title: '论文甲' }, { id: 'b', title: '论文乙' }];
    const send = vi.fn().mockResolvedValue(false);
    const view = renderChat({ enableSkills: true, conversationId: 'scope', materials, onSendMessage: send });
    fireEvent.click(screen.getByRole('button', { name: '对话材料' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '论文乙' }));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('button', { name: '发送消息' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '解释方法 \n' } });
    expect(screen.getByLabelText('输入问题')).toHaveValue('解释方法 \n');
    view.unmount();
    renderChat({ enableSkills: true, conversationId: 'scope', materials, onSendMessage: send });
    expect(screen.getByLabelText('输入问题')).toHaveValue('解释方法 \n');
    expect(screen.getByRole('button', { name: '移除材料 论文乙' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '只解释直觉' } });
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    await waitFor(() => expect(send).toHaveBeenCalledExactlyOnceWith('只解释直觉 @{论文乙}'));
    fireEvent.click(screen.getByRole('button', { name: '移除材料 论文乙' }));
    expect(screen.getByLabelText('输入问题')).toHaveValue('只解释直觉');
    expect(screen.getByText('全部材料 · 2篇')).toBeInTheDocument();
  });

  it('adds an @ completion as a chip while preserving prose and a previously selected material', () => {
    renderChat({ enableSkills: true, materials: [{ id: 'a', title: '论文甲' }, { id: 'b', title: '论文乙' }] });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '比较方法 @{论文甲}' } });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '比较方法 @乙' } });
    fireEvent.click(screen.getByRole('button', { name: '论文乙', exact: true }));
    expect(screen.getByLabelText('输入问题').value.trim()).toBe('比较方法');
    expect(screen.getByRole('button', { name: '移除材料 论文甲' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '移除材料 论文乙' })).toBeInTheDocument();
  });

  it('keeps next steps folded and preserves an existing question instead of overwriting it', () => {
    const select = vi.fn();
    renderChat({ messages: [{ role: 'ai', content: '现有回答' }], starterPrompts: [{ label: '下一步行动', text: '', onSelect: select }] });
    expect(screen.getByText('下一步').closest('details')).not.toHaveAttribute('open');
    fireEvent.click(screen.getByRole('button', { name: '下一步行动' }));
    expect(select).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '我自己的问题' } });
    expect(screen.queryByText('下一步')).not.toBeInTheDocument();
    expect(screen.getByLabelText('输入问题')).toHaveValue('我自己的问题');
  });
  it('distinguishes all materials, explicit selections and the paper being read', () => {
    renderChat({ enableSkills: true, focusedMaterialId: 'a', materials: [{ id: 'a', title: '论文甲' }, { id: 'b', title: '论文乙' }] });
    expect(screen.queryByRole('button', { name: '@ 材料' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '解释这个方法' } });
    fireEvent.click(screen.getByRole('button', { name: '对话材料' }));
    expect(screen.getByText('本轮对话材料')).toBeInTheDocument();
    expect(screen.getByText('阅读中').closest('label')).toContainElement(screen.getByRole('checkbox', { name: '论文甲' }));
    expect(screen.getByRole('button', { name: '使用本任务全部材料' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('checkbox', { name: '论文甲' })).not.toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: '论文甲' }));
    const input = screen.getByLabelText('输入问题');
    expect(input).toHaveValue('解释这个方法');
    expect(screen.getByRole('checkbox', { name: '论文甲' })).toBeChecked();
    expect(screen.getByRole('button', { name: '使用本任务全部材料' })).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByRole('checkbox', { name: '论文乙' }));
    expect(screen.getByText('已指定 2 篇')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: '论文甲' }));
    expect(input.value.trim()).toBe('解释这个方法');
    expect(screen.getByText('指定材料 · 1篇')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: '论文乙' }));
    expect(input.value.trim()).toBe('解释这个方法');
    expect(screen.getByRole('button', { name: '使用本任务全部材料' })).toHaveAttribute('aria-pressed', 'true');
  });
  it('expands the same draft and material scope, then returns with Escape without sending', () => {
    const send = vi.fn();
    renderChat({ enableSkills: true, conversationId: 'expanded', onSendMessage: send, materials: [{ id: 'a', title: '论文甲' }] });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '只根据 @{论文甲} 请帮我设计实验' } });
    fireEvent.click(screen.getByRole('button', { name: '展开输入' }));
    const dialog = screen.getByRole('dialog', { name: '全屏输入' });
    expect(screen.getByLabelText('输入问题')).toHaveFocus();
    expect(screen.getByText('指定材料 · 1篇')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '只根据 @{论文甲} 请帮我设计实验\n再列出对照条件' } });
    fireEvent(dialog, new Event('cancel', { bubbles: false, cancelable: true }));
    expect(screen.queryByRole('dialog', { name: '全屏输入' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('输入问题')).toHaveValue('只根据 请帮我设计实验\n再列出对照条件');
    expect(screen.getByRole('button', { name: '展开输入' })).toHaveFocus();
    expect(send).not.toHaveBeenCalled();
  });
  it('uses Enter for fullscreen writing and Ctrl+Enter to send and return to chat', async () => {
    const send = vi.fn().mockResolvedValue(true);
    renderChat({ onSendMessage: send });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '多行问题' } });
    fireEvent.click(screen.getByRole('button', { name: '展开输入' }));
    fireEvent.keyDown(screen.getByLabelText('输入问题'), { key: 'Enter' });
    expect(send).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByLabelText('输入问题'), { key: 'Enter', ctrlKey: true });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '全屏输入' })).not.toBeInTheDocument());
    expect(send).toHaveBeenCalledExactlyOnceWith('多行问题');
    expect(screen.getByLabelText('输入问题')).toHaveValue('');
  });
  it('keeps a failed fullscreen submission visible and editable', async () => {
    renderChat({ onSendMessage: vi.fn().mockRejectedValue(new Error('网络不可用')) });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '保留这个问题' } });
    fireEvent.click(screen.getByRole('button', { name: '展开输入' }));
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('网络不可用'));
    expect(screen.getByRole('dialog', { name: '全屏输入' })).toContainElement(screen.getByRole('alert'));
    expect(screen.getByLabelText('输入问题')).toHaveValue('保留这个问题');
    fireEvent.click(screen.getByRole('button', { name: '收起输入' }));
    expect(screen.getByLabelText('输入问题')).toHaveValue('保留这个问题');
  });
  it('selects materials without sending and returns to the preserved question', async () => {
    const send = vi.fn();
    renderChat({ enableSkills: true, onSendMessage: send, materials: [{ id: 'a', title: '论文甲' }, { id: 'b', title: '论文乙' }] });
    const input = screen.getByRole('textbox', { name: '输入问题' });
    fireEvent.change(input, { target: { value: '解释这个方法' } });
    fireEvent.click(screen.getByRole('button', { name: '对话材料' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '论文甲' }));
    fireEvent.click(screen.getByRole('button', { name: '完成' }));
    await waitFor(() => expect(input).toHaveFocus());
    expect(input).toHaveValue('解释这个方法');
    expect(send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '对话材料' }));
    fireEvent.click(screen.getByRole('button', { name: '使用本任务全部材料' }));
    expect(input.value.trim()).toBe('解释这个方法');
    expect(screen.getByText('全部材料 · 2篇')).toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });
  it('uses identical outside, Escape and menu-switch dismissal for both pickers', () => {
    const send = vi.fn();
    renderChat({ enableSkills: true, onSendMessage: send, materials: [{ id: 'a', title: '论文甲' }] });
    for (const name of ['对话材料', '功能']) {
      const trigger = screen.getByRole('button', { name, exact: true });
      fireEvent.click(trigger);
      expect(screen.getByRole('dialog', { name, exact: true })).toBeInTheDocument();
      fireEvent.pointerDown(document.body);
      expect(screen.queryByRole('dialog', { name, exact: true })).not.toBeInTheDocument();
      fireEvent.click(trigger);
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(screen.queryByRole('dialog', { name, exact: true })).not.toBeInTheDocument();
      expect(trigger).toHaveFocus();
    }
    fireEvent.click(screen.getByRole('button', { name: '对话材料', exact: true }));
    const functions = screen.getByRole('button', { name: '功能', exact: true });
    fireEvent.pointerDown(functions); fireEvent.click(functions);
    expect(screen.queryByRole('dialog', { name: '对话材料', exact: true })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '/精读', exact: true }));
    expect(screen.getByLabelText('输入问题')).toHaveValue('/精读 ');
    expect(screen.getByLabelText('输入问题')).toHaveFocus();
    expect(screen.queryByRole('dialog', { name: '功能', exact: true })).not.toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });
  it('dismisses typed slash and mention suggestions without deleting the draft', () => {
    renderChat({ enableSkills: true, materials: [{ id: 'a', title: '论文甲' }] });
    const input = screen.getByLabelText('输入问题');
    for (const [text, name] of [['/', '功能命令'], ['解释 @', '选择任务材料']]) {
      fireEvent.change(input, { target: { value: text } });
      expect(screen.getByRole('group', { name })).toBeInTheDocument();
      fireEvent.pointerDown(document.body);
      expect(screen.queryByRole('group', { name })).not.toBeInTheDocument();
      expect(input).toHaveValue(text);
      fireEvent.change(input, { target: { value: `${text}甲` } });
      fireEvent.change(input, { target: { value: text } });
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(screen.queryByRole('group', { name })).not.toBeInTheDocument();
      expect(input).toHaveValue(text);
    }
  });
  it('keeps materials with identical titles independently selectable by ID', () => {
    renderChat({ enableSkills: true, materials: [{ id: 'a', title: '同名论文' }, { id: 'b', title: '同名论文' }] });
    fireEvent.click(screen.getByRole('button', { name: '对话材料' }));
    const [first, second] = screen.getAllByRole('checkbox', { name: '同名论文' });
    fireEvent.click(first);
    expect(first).toBeChecked(); expect(second).not.toBeChecked();
    fireEvent.click(second); fireEvent.click(first);
    expect(screen.getByLabelText('输入问题').value.trim()).toBe('');
    expect(second).toBeChecked();
  });
  it('marks a retained old answer and opens the current document explicitly', () => {
    const open = vi.fn();
    renderChat({ messages: [{ id: 'old', role: 'ai', content: '旧判断', artifactId: 'report', artifactIsCurrent: false }], onOpenArtifact: open });
    expect(screen.getByText(/此回答对应旧版本/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看当前成果' }));
    expect(open).toHaveBeenCalledWith('report');
    expect(screen.getByText('旧判断')).toBeInTheDocument();
  });
  it('fills a suggested question without starting any generation', () => {
    const send = vi.fn();
    renderChat({ starterPrompts: [{ label: '带我读这篇', text: '/精读 从研究问题开始' }], onSendMessage: send });
    fireEvent.click(screen.getByRole('button', { name: '带我读这篇' }));
    expect(screen.getByLabelText('输入问题')).toHaveValue('/精读 从研究问题开始');
    expect(screen.getByLabelText('输入问题')).toHaveFocus();
    expect(send).not.toHaveBeenCalled();
  });

  it('keeps drafts separate when tasks switch and restores them after remounting', () => {
    const view = renderChat({ conversationId: 'A' });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: 'A 的问题' } });
    view.rerender(<ChatPanel {...defaultProps} conversationId="B" />);
    expect(screen.getByLabelText('输入问题')).toHaveValue('');
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: 'B 的问题' } });
    view.rerender(<ChatPanel {...defaultProps} conversationId="A" />);
    expect(screen.getByLabelText('输入问题')).toHaveValue('A 的问题');
    view.unmount();
    renderChat({ conversationId: 'B' });
    expect(screen.getByLabelText('输入问题')).toHaveValue('B 的问题');
  });

  it('keeps rejected or failed questions available for editing', async () => {
    const send = vi.fn().mockResolvedValueOnce(false).mockRejectedValueOnce(new Error('连接中断'));
    renderChat({ conversationId: 'A', onSendMessage: send });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '/精读 我的目标' } });
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '发送消息' })).toBeEnabled());
    expect(screen.getByLabelText('输入问题')).toHaveValue('/精读 我的目标');
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('连接中断');
    expect(screen.getByLabelText('输入问题')).toHaveValue('/精读 我的目标');
  });

  it('does not let a late accepted submission clear a newer draft in the same task', async () => {
    let finish;
    const send = vi.fn(() => new Promise(resolve => { finish = resolve; }));
    const first = renderChat({ conversationId: 'A', onSendMessage: send });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '原问题' } });
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    expect(send).toHaveBeenCalledTimes(1);
    first.unmount();
    const second = renderChat({ conversationId: 'A' });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '新草稿' } });
    await act(async () => finish(true));
    second.unmount();
    renderChat({ conversationId: 'A' });
    expect(screen.getByLabelText('输入问题')).toHaveValue('新草稿');
  });
  it('opens the existing full artifact instead of saving a second copy of the summary', () => {
    const open = vi.fn();
    const capture = vi.fn();
    renderChat({ messages: [{ role: 'ai', content: '简短结论', artifactId: 'full' }], onOpenArtifact: open, onCaptureArtifact: capture });
    fireEvent.click(screen.getByRole('button', { name: '打开完整成果' }));
    expect(open).toHaveBeenCalledWith('full');
    expect(capture).not.toHaveBeenCalled();
  });
  it('completes an @ material mention without losing the preceding question', () => {
    const send = vi.fn();
    renderChat({ enableSkills: true, onSendMessage: send, materials: [{ id: 'b', title: '论文乙' }] });
    fireEvent.change(screen.getByLabelText('输入问题'), { target: { value: '只根据 @乙' } });
    fireEvent.click(screen.getByRole('button', { name: '论文乙', exact: true }));
    expect(screen.getByLabelText('输入问题')).toHaveValue('只根据');
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    expect(send).toHaveBeenCalledWith('只根据 @{论文乙}');
  });
  it('renders input textarea', () => {
    renderChat();
    const textarea = screen.getByLabelText('输入问题');
    expect(textarea).toBeInTheDocument();
    expect(textarea).not.toBeDisabled();
  });

  it('keeps the next draft editable while loading and prevents another send', () => {
    renderChat({ isLoading: true });
    const textarea = screen.getByLabelText('输入问题');
    expect(textarea).toBeEnabled();
    fireEvent.change(textarea, { target: { value: '下一条草稿' } });
    expect(screen.getByRole('button', { name: '发送消息' })).toBeDisabled();
    expect(screen.getAllByRole('button', { name: '停止生成' })).toHaveLength(1);
    expect(screen.getByRole('button', { name: '停止生成' }).closest('.workbench-composer-container')).toBe(textarea.closest('.workbench-composer-container'));
  });

  it('calls onSendMessage when typing and clicking send', () => {
    const onSend = vi.fn();
    renderChat({ onSendMessage: onSend });

    const textarea = screen.getByLabelText('输入问题');
    fireEvent.change(textarea, { target: { value: '这篇论文的核心贡献？' } });

    const sendButton = screen.getByRole('button', { name: '发送消息' });
    fireEvent.click(sendButton);

    expect(onSend).toHaveBeenCalledWith('这篇论文的核心贡献？');
  });

  it('sends message on Enter key', () => {
    const onSend = vi.fn();
    renderChat({ onSendMessage: onSend });

    const textarea = screen.getByLabelText('输入问题');
    fireEvent.change(textarea, { target: { value: 'Hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(onSend).toHaveBeenCalledWith('Hello');
  });

  it('does not send on Shift+Enter', () => {
    const onSend = vi.fn();
    renderChat({ onSendMessage: onSend });

    const textarea = screen.getByLabelText('输入问题');
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
    expect(screen.getByText('生成中')).toBeInTheDocument();
    // The loading indicator shows a pulsing progress bar
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
    const textarea = screen.getByLabelText('输入问题');
    const sendButton = screen.getByRole('button', { name: '发送消息' });
    expect(sendButton).toBeDisabled();
  });

  it('renders the current reading context', () => {
    renderChat({ contextLabel: '第 8 页 · Method' });
    expect(screen.getByText(/第 8 页 · Method/)).toBeInTheDocument();
  });

  it('calls onDeleteMessage on message delete', () => {
    const onDelete = vi.fn();
    const messages = [{ id: 1, role: 'ai', content: '回答内容' }];
    const originalConfirm = window.confirm;
    window.confirm = vi.fn(() => true);

    renderChat({ messages, onDeleteMessage: onDelete });

    fireEvent.click(screen.getByRole('button', { name: '消息更多操作' }));
    fireEvent.click(screen.getByTitle('删除此消息'));

    expect(window.confirm).toHaveBeenCalled();
    expect(onDelete).toHaveBeenCalledWith(0);

    window.confirm = originalConfirm;
  });
});


describe('ChatPanel interaction continuity', () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); vi.clearAllMocks(); });

  it('retains edits made during an accepted request and ignores IME confirmation', async () => {
    let finish;
    const send = vi.fn(() => new Promise(resolve => { finish = resolve; }));
    renderChat({ conversationId: 'editable', onSendMessage: send });
    const input = screen.getByLabelText('输入问题');
    fireEvent.change(input, { target: { value: '原问题' } });
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
    expect(send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    expect(input).toBeEnabled();
    fireEvent.change(input, { target: { value: '新的草稿' } });
    await act(async () => finish(true));
    expect(input).toHaveValue('新的草稿');
  });

  it('removes explicit material and function choices only from the draft', () => {
    const send = vi.fn();
    renderChat({ enableSkills: true, materials: [{ id: 'm', title: '论文甲' }], onSendMessage: send });
    const input = screen.getByLabelText('输入问题');
    fireEvent.change(input, { target: { value: '/比较 根据 @{论文甲} 回答' } });
    fireEvent.click(screen.getByRole('button', { name: '移除材料 论文甲' }));
    expect(input).toHaveValue('/比较 根据 回答');
    fireEvent.click(screen.getByRole('button', { name: '取消比较功能' }));
    expect(input).toHaveValue('根据 回答');
    expect(send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '功能', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: '/批判', exact: true }));
    expect(input).toHaveValue('/批判 根据 回答');
  });

  it('uses one save action, prevents concurrent and repeated saves, and exposes progress', async () => {
    let finish;
    const capture = vi.fn(() => new Promise(resolve => { finish = resolve; }));
    const note = vi.fn();
    const messages = [{ id: 'answer', role: 'ai', content: '回答' }];
    const view = renderChat({ messages, onCaptureArtifact: capture, onSaveToNote: note });
    expect(screen.queryByRole('button', { name: '收藏到学术笔记' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    expect(screen.getByRole('button', { name: '保存中' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '保存中' }));
    expect(capture).toHaveBeenCalledTimes(1);
    expect(note).not.toHaveBeenCalled();
    await act(async () => finish());
    expect(screen.getByRole('button', { name: '已保存' })).toBeDisabled();
    view.rerender(<ChatPanel {...defaultProps} messages={[{ ...messages[0], artifactId: 'saved' }]} onCaptureArtifact={capture} />);
    expect(screen.getByRole('button', { name: '打开完整成果' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '已保存' })).not.toBeInTheDocument();
  });

  it('offers an explicit note link after saving without opening it automatically', async () => {
    const save = vi.fn().mockResolvedValue('note-id'), open = vi.fn();
    renderChat({ messages: [{ id: 'u', role: 'user', content: '我的想法' }], onSaveToNote: save, onOpenArtifact: open });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    const link = await screen.findByRole('button', { name: '查看笔记' });
    expect(open).not.toHaveBeenCalled();
    expect(link).toHaveTextContent('已保存');
    fireEvent.click(link);
    expect(open).toHaveBeenCalledWith('note-id');
  });

  it('searches original messages and supports anchored content and parent focus requests', () => {
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView');
    const messages = [{ id: 'question', role: 'user', content: '比较论文甲' }, { id: 'answer', role: 'ai', content: '比较结果' }];
    const after = (message, index) => <span>活动 {message.id} {index}</span>;
    const view = renderChat({ messages, renderMessageAfter: after, historyContent: <p>处理记录</p>, composerContext: <span>当前材料</span>, contextLabel: '旧上下文', currentActivity: <span>等待确认</span> });
    expect(screen.getByText('活动 question 0').closest('[data-message-id]')).toHaveAttribute('data-message-id', 'question');
    expect(screen.getByText('处理记录')).toBeInTheDocument();
    expect(screen.queryByText(/旧上下文/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查找对话' }));
    fireEvent.change(screen.getByLabelText('搜索对话'), { target: { value: '论文甲' } });
    fireEvent.click(screen.getByRole('button', { name: '第 1 条 · 比较论文甲' }));
    expect(scroll.mock.instances.at(-1)).toHaveAttribute('data-message-id', 'question');
    expect(screen.getByText('比较论文甲').closest('[data-message-id]')).toHaveClass('chat-message-highlight');
    view.rerender(<ChatPanel {...defaultProps} messages={messages} focusMessage={{ id: 'answer', token: 1 }} />);
    expect(scroll.mock.instances.at(-1)).toHaveAttribute('data-message-id', 'answer');
    scroll.mockRestore();
  });

  it('preserves browsing position, announces new results and restores each task scroll', () => {
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView');
    const initial = [{ id: 1, role: 'ai', content: '旧消息' }];
    const view = renderChat({ messages: initial, conversationId: 'scroll-A' });
    const scroller = view.container.querySelector('.reader-chat-scroll');
    Object.defineProperties(scroller, { scrollHeight: { configurable: true, value: 1200 }, clientHeight: { configurable: true, value: 300 } });
    scroller.scrollTop = 120;
    fireEvent.scroll(scroller);
    scroll.mockClear();
    const updated = [...initial, { id: 2, role: 'ai', content: '新回答' }];
    view.rerender(<ChatPanel {...defaultProps} messages={updated} conversationId="scroll-A" />);
    expect(scroll).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '有新结果 · 查看最新' })).toBeInTheDocument();
    view.rerender(<ChatPanel {...defaultProps} messages={[]} conversationId="scroll-B" />);
    scroller.scrollTop = 320;
    fireEvent.scroll(scroller);
    view.rerender(<ChatPanel {...defaultProps} messages={updated} conversationId="scroll-A" />);
    expect(scroller.scrollTop).toBe(120);
    view.unmount();
    const restored = renderChat({ messages: updated, conversationId: 'scroll-A' });
    expect(restored.container.querySelector('.reader-chat-scroll').scrollTop).toBe(120);
    scroll.mockRestore();
  });

  it('allows the parent to replace loading presentation while preserving the stop action', () => {
    renderChat({ isLoading: true, showLoadingIndicator: false, currentActivity: <span>研究中</span> });
    expect(screen.queryByText('生成中')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '停止生成' })).toBeInTheDocument();
  });
});


it('announces slot-only results while browsing and jumps to the newest result on demand', async () => {
  const scroll = vi.spyOn(Element.prototype, 'scrollIntoView');
  const messages = [{ id: 'request', role: 'user', content: '研究问题' }];
  const view = renderChat({ conversationId: 'slot-results', messages, renderMessageAfter: () => <span>运行中</span> });
  const scroller = view.container.querySelector('.reader-chat-scroll');
  Object.defineProperties(scroller, { scrollHeight: { configurable: true, value: 1000 }, clientHeight: { configurable: true, value: 200 } });
  scroller.scrollTop = 50;
  fireEvent.scroll(scroller);
  scroll.mockClear();
  view.rerender(<ChatPanel {...defaultProps} conversationId="slot-results" messages={messages} renderMessageAfter={() => <span>报告已完成</span>} />);
  await waitFor(() => expect(screen.getByRole('button', { name: '有新结果 · 查看最新' })).toBeInTheDocument());
  expect(scroll).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '有新结果 · 查看最新' }));
  expect(scroll).toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: '有新结果 · 查看最新' })).not.toBeInTheDocument();
  scroll.mockRestore();
});

it('retries failed saves and lets a user message use the same visible save entry', async () => {
  const note = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined);
  renderChat({ messages: [{ id: 'user-save', role: 'user', content: '我的问题' }], onSaveToNote: note });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('保存失败');
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '已保存' })).toBeInTheDocument());
  expect(note).toHaveBeenCalledTimes(2);
  expect(note).toHaveBeenLastCalledWith(0);
});
