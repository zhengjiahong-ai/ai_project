import type { ResolvedTaskContext } from './taskWorkspaceModel';

type Message = {
  role?: string;
  content?: string;
  isSystem?: boolean;
  context?: ResolvedTaskContext;
};

/** Unknown legacy provenance cannot establish permission to reuse paper-derived text. */
export function taskChatHistory(messages: Message[], scope: ResolvedTaskContext) {
  const allowed = new Set(scope.allowedPaperIds);
  return messages.filter((message) => {
    if (message.isSystem || !['user', 'ai', 'assistant'].includes(message.role || '')) return false;
    const previous = message.context;
    return previous?.taskId === scope.taskId
      && previous.allowedPaperIds.every((id) => allowed.has(id));
  }).slice(-20).map((message) => ({
    role: message.role === 'ai' ? 'assistant' : message.role,
    content: message.content || '',
  }));
}
