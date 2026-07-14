import { useState } from 'react';
import { HelpCircle, Send, Loader2, MessageSquare } from 'lucide-react';

export default function ClarificationCard({ questions = [], roundNumber = 1, onAnswer, disabled = false }) {
  const [answer, setAnswer] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!questions.length) return null;

  const handleSubmit = async () => {
    if (!answer.trim() || submitting || disabled) return;
    setSubmitting(true);
    try {
      await onAnswer?.(answer.trim());
      setAnswer('');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="clarification-card rounded border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/10 overflow-hidden">
      <div className="p-3 border-b border-amber-200 dark:border-amber-800">
        <div className="flex items-center gap-2">
          <HelpCircle size={16} className="text-amber-500" />
          <span className="text-sm font-semibold text-amber-700 dark:text-amber-400">
            研究追问 · 第 {roundNumber}/3 轮
          </span>
        </div>
        <p className="text-xs text-amber-600 dark:text-amber-500 mt-1">
          AI 需要更多信息来继续研究。请回答以下问题：
        </p>
      </div>

      <div className="p-3 space-y-3">
        {questions.map((q, i) => (
          <div key={i} className="space-y-1">
            <div className="flex items-start gap-2">
              <MessageSquare size={14} className="text-pixiu-muted mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium text-pixiu">{q.question}</p>
                {q.context && (
                  <p className="text-xs text-pixiu-muted mt-0.5">{q.context}</p>
                )}
              </div>
            </div>
          </div>
        ))}

        <div className="space-y-2">
          <textarea
            className="w-full p-2 rounded bg-pixiu-bg border border-pixiu-border text-pixiu text-sm resize-none"
            rows={3}
            placeholder="输入你的回答..."
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={disabled || submitting}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                handleSubmit();
              }
            }}
          />
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-pixiu-accent text-white text-sm font-medium disabled:opacity-50"
            onClick={handleSubmit}
            disabled={!answer.trim() || disabled || submitting}
          >
            {submitting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
            提交回答 (⌘Enter)
          </button>
        </div>
      </div>
    </div>
  );
}
