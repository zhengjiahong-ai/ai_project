import { useState } from 'react';
import { ChevronDown, ChevronRight, Gavel, ThumbsUp, ThumbsDown, Trophy } from 'lucide-react';

export default function ConflictAdjudicationCard({ result = {} }) {
  const [expanded, setExpanded] = useState(false);

  const proScore = result?.proScore ?? {};
  const conScore = result?.conScore ?? {};
  const winner = result?.winner ?? '';
  const reasoning = result?.reasoning ?? '';

  if (!result?.status && !winner) return null;

  return (
    <div className="conflict-adjudication-card rounded border border-pixiu-border overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-3 hover:bg-pixiu-surface/50 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <Gavel size={16} className="text-amber-500" />
          <span className="text-sm font-medium text-pixiu">矛盾裁决</span>
          {winner && (
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
              winner === 'pro' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
              winner === 'con' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
              'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
            }`}>
              {winner === 'pro' ? '支持方胜出' : winner === 'con' ? '反对方胜出' : '平局'}
            </span>
          )}
        </div>
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>

      {expanded && (
        <div className="p-3 space-y-3 border-t border-pixiu-border">
          {/* Pro vs Con comparison */}
          <div className="grid grid-cols-2 gap-3">
            {/* Pro side */}
            <div className="p-2 rounded bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800">
              <div className="flex items-center gap-1.5 mb-2">
                <ThumbsUp size={14} className="text-green-500" />
                <span className="text-xs font-semibold text-green-700 dark:text-green-400">支持方</span>
              </div>
              <div className="space-y-1 text-xs text-pixiu">
                {Object.entries(proScore).map(([key, val]) => (
                  <div key={key} className="flex justify-between">
                    <span className="text-pixiu-muted">{key}</span>
                    <span className="font-mono font-medium">{typeof val === 'number' ? val.toFixed(2) : val}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Con side */}
            <div className="p-2 rounded bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800">
              <div className="flex items-center gap-1.5 mb-2">
                <ThumbsDown size={14} className="text-red-500" />
                <span className="text-xs font-semibold text-red-700 dark:text-red-400">反对方</span>
              </div>
              <div className="space-y-1 text-xs text-pixiu">
                {Object.entries(conScore).map(([key, val]) => (
                  <div key={key} className="flex justify-between">
                    <span className="text-pixiu-muted">{key}</span>
                    <span className="font-mono font-medium">{typeof val === 'number' ? val.toFixed(2) : val}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Score bar comparison */}
          {result?.confidence != null && (
            <div>
              <div className="flex justify-between text-xs text-pixiu-muted mb-1">
                <span>综合置信度</span>
                <span className="font-mono">{(result.confidence * 100).toFixed(0)}%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-pixiu-surface overflow-hidden">
                <div
                  className="h-2 rounded-full bg-pixiu-accent transition-all"
                  style={{ width: `${Math.round(result.confidence * 100)}%` }}
                />
              </div>
            </div>
          )}

          {/* Reasoning */}
          {reasoning && (
            <div className="p-2 rounded bg-pixiu-surface text-xs text-pixiu">
              <span className="font-medium">推理: </span>
              {reasoning.slice(0, 500)}
            </div>
          )}

          {/* Winner highlight */}
          {winner && (
            <div className="flex items-center gap-2 p-2 rounded bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800 text-xs">
              <Trophy size={14} className="text-amber-500" />
              <span className="font-medium text-amber-700 dark:text-amber-400">
                {result?.recommendation ?? `建议采纳${winner === 'pro' ? '支持方' : '反对方'}观点`}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
