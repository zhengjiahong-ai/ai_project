import { useCallback, useMemo, useState } from 'react';

const draftKey = id => `pixiu-conversation-draft:${JSON.stringify(id)}`;
const readDraft = id => {
  if (!id) return '';
  try { return localStorage.getItem(draftKey(id)) || ''; } catch { return ''; }
};

/** Keep unsent questions separate from saved messages and scoped to their task. */
export default function useConversationDraft(conversationId) {
  const [drafts, setDrafts] = useState({});
  const [errors, setErrors] = useState({});
  const persisted = useMemo(() => readDraft(conversationId), [conversationId]);
  const owner = conversationId || 'legacy';
  const value = Object.hasOwn(drafts, owner) ? drafts[owner] : persisted;
  const setValue = useCallback(next => {
    setDrafts(previous => ({ ...previous, [owner]: next }));
    if (!conversationId) return;
    try {
      if (next) localStorage.setItem(draftKey(conversationId), next);
      else localStorage.removeItem(draftKey(conversationId));
      setErrors(previous => ({ ...previous, [owner]: '' }));
    } catch {
      setErrors(previous => ({ ...previous, [owner]: '输入草稿暂时无法保存，请保留当前内容。' }));
    }
  }, [conversationId, owner]);
  const clearValue = useCallback(expected => {
    if (conversationId) {
      try {
        if (localStorage.getItem(draftKey(conversationId)) !== expected) return;
      } catch { return; }
    }
    setValue('');
  }, [conversationId, setValue]);
  return [value, setValue, errors[owner] || '', clearValue];
}
