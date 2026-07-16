import { useCallback } from 'react';

/**
 * Encapsulates chat-related handlers: send, abort, delete, explain,
 * jump-to-source, save-to-note, and capture-artifact.
 *
 * All state that lives in the parent (messages, pdfId, papersList, etc.)
 * is passed in as parameters so this hook stays pure.
 */
export function useChat({
  apiService,
  pdfId,
  messages,
  setMessages,
  setActiveTab,
  deconstructData,
  papersList,
  //
  startChatRequest,
  finishChatRequest,
  abortChatRequest,
  isChatLoading,
  //
  addNote,
  captureArtifact,
  //
  restorePaperState,
  jumpToPage,
  setAppMode,
  setFocusedSourceRequest,
  showWarning,
}) {
  const handleSendMessage = useCallback((message) => {
    if (!pdfId || isChatLoading(pdfId)) return;

    setActiveTab('chat');
    setMessages((prev) => [...prev, { role: 'user', content: message }]);

    const controller = startChatRequest(pdfId);
    if (!controller) return;

    const history = messages.slice(-6).map((item) => ({
      role: item.role === 'ai' ? 'assistant' : item.role,
      content: item.content,
    }));

    apiService
      .sendMessage(message, pdfId, history, deconstructData?.paper_skeleton || null, controller.signal)
      .then((response) => {
        const content = response?.reply ?? response?.message ?? response?.data?.reply ?? '暂无回复';
        const sentenceSourceMap = response?.sentenceSourceMap ?? response?.data?.sentenceSourceMap ?? [];
        const ragSources = response?.rag_sources ?? response?.data?.rag_sources ?? [];
        setMessages((prev) => [...prev, {
          role: 'ai',
          content,
          sentenceSourceMap,
          rag_sources: ragSources,
        }]);
      })
      .catch((error) => {
        if (error.name === 'CanceledError' || error.message === 'canceled') {
          return;
        }

        const errMsg = error?.response?.data?.message ?? error?.message ?? '请求失败，请稍后重试';
        setMessages((prev) => [
          ...prev,
          { role: 'ai', content: `抱歉，处理您的请求时出现了错误：${errMsg}` },
        ]);
      })
      .finally(() => {
        finishChatRequest(pdfId);
      });
  }, [deconstructData, finishChatRequest, isChatLoading, messages, pdfId, startChatRequest, setActiveTab, setMessages]);

  const handleAbortChat = useCallback((targetPdfId) => {
    const wasAborted = abortChatRequest(targetPdfId);
    if (!wasAborted) return;
    setMessages((prev) => [...prev, { role: 'ai', isSystem: true, content: '本次回答已由用户取消。' }]);
  }, [abortChatRequest, setMessages]);

  const handleDeleteChatMessage = useCallback((index) => {
    setMessages((prev) => {
      const targetMessage = prev[index];
      if (!targetMessage) return prev;

      const indexesToDelete = [index];
      if (targetMessage.role === 'user' && prev[index + 1]?.role === 'ai') {
        indexesToDelete.push(index + 1);
      }
      if (targetMessage.role === 'ai' && prev[index - 1]?.role === 'user') {
        indexesToDelete.push(index - 1);
      }

      return prev.filter((_, currentIndex) => !indexesToDelete.includes(currentIndex));
    });
  }, [setMessages]);

  const handleExplain = useCallback((content, role = 'user', isSyncOnly = false, sourceMeta = null) => {
    if (role === 'user' && !isSyncOnly) {
      handleSendMessage(`请解释以下内容：${content}`);
      return;
    }

    setMessages((prev) => [
      ...prev,
      {
        role,
        content,
        id: Date.now(),
        sourceAnchorId: sourceMeta?.sourceAnchorId || null,
        sourcePageIndex: sourceMeta?.sourcePageIndex ?? null,
        sourceText: sourceMeta?.sourceText || '',
        sourceActionId: sourceMeta?.sourceActionId || null,
        sourceActionLabel: sourceMeta?.sourceActionLabel || '',
      },
    ]);
  }, [handleSendMessage, setMessages]);

  const handleJumpToSource = useCallback(async (message) => {
    const pageIndex = Number.isFinite(message?.sourcePageIndex)
      ? message.sourcePageIndex
      : Number.isFinite(message?.pageIndex)
        ? message.pageIndex
        : null;
    const anchorId = message?.sourceAnchorId || message?.sectionId || message?.sourceId || null;
    const targetPdfId = `${message?.pdfId ?? ''}`.trim();

    if (!anchorId && !Number.isFinite(pageIndex)) {
      return false;
    }

    if (targetPdfId && targetPdfId !== pdfId) {
      const hasTargetPaper = papersList.some((paper) => `${paper?.id ?? ''}`.trim() === targetPdfId);
      if (!hasTargetPaper) {
        return false;
      }

      const didRestore = await restorePaperState(targetPdfId);
      if (!didRestore) {
        return false;
      }
    } else if (Number.isFinite(pageIndex) && !pdfId) {
      return false;
    }

    setAppMode('reader');
    if (Number.isFinite(pageIndex)) {
      jumpToPage(pageIndex);
    }

    if (anchorId) {
      setFocusedSourceRequest({
        anchorId,
        token: Date.now(),
      });
    }
    return true;
  }, [jumpToPage, papersList, pdfId, restorePaperState, setAppMode, setFocusedSourceRequest]);

  const handleSaveChatToNote = useCallback((index) => {
    const message = messages[index];
    if (!message) return;

    let question = '';
    let answer = '';

    if (message.role === 'user') {
      question = message.content;
      const nextMessage = messages[index + 1];
      answer = nextMessage?.role === 'ai' ? nextMessage.content : '等待 AI 回答中...';
    } else {
      answer = message.content;
      const previousMessage = messages[index - 1];
      question = previousMessage?.role === 'user' ? previousMessage.content : '提问内容定位失败';
    }

    const sourceMessage =
      message.sourceAnchorId
        ? message
        : message.role === 'user'
          ? messages[index + 1]
          : messages[index - 1];

    addNote({
      text: question,
      aiInterpretation: answer,
      pageNumber: -1,
      sourceAnchorId: sourceMessage?.sourceAnchorId || null,
      sourcePageIndex: sourceMessage?.sourcePageIndex ?? null,
      sourceActionId: sourceMessage?.sourceActionId || null,
      sourceActionLabel: sourceMessage?.sourceActionLabel || '',
    });

    if (typeof showWarning === 'function') {
      showWarning('已将该对话内容收藏至"学术笔记"中。');
    }
  }, [addNote, messages, showWarning]);

  const handleCaptureChatArtifact = useCallback((index) => {
    const message = messages[index];
    if (!message) {
      return;
    }

    let question = '';
    let answer = '';

    if (message.role === 'user') {
      question = message.content;
      const nextMessage = messages[index + 1];
      answer = nextMessage?.role === 'ai' ? nextMessage.content : message.content;
    } else {
      answer = message.content;
      const previousMessage = messages[index - 1];
      question = previousMessage?.role === 'user' ? previousMessage.content : '未关联到上一条提问';
    }

    const sourceMessage =
      message.sourceAnchorId
        ? message
        : message.role === 'user'
          ? messages[index + 1]
          : messages[index - 1];

    captureArtifact({
      kind: 'chat-answer',
      title: question.length > 36 ? `${question.slice(0, 36)}...` : question,
      summary: answer,
      content: `### 提问\n${question}\n\n### 回答\n${answer}`,
      sourceMessageId: `${message.id ?? index}`,
      pageIndex: sourceMessage?.sourcePageIndex ?? null,
      sourceAnchorId: sourceMessage?.sourceAnchorId || null,
      sourceActionId: sourceMessage?.sourceActionId || null,
      sourceActionLabel: sourceMessage?.sourceActionLabel || '',
      tags: ['chat', 'qa'],
    });
  }, [captureArtifact, messages]);

  return {
    handleSendMessage,
    handleAbortChat,
    handleDeleteChatMessage,
    handleExplain,
    handleJumpToSource,
    handleSaveChatToNote,
    handleCaptureChatArtifact,
  };
}
