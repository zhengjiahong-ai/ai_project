import { useState } from 'react';
import { ChevronDown, ChevronRight, ShieldAlert, TrendingDown, AlertTriangle, Search } from 'lucide-react';

const SEVERITY_CONFIG = {
  high: { color: 'text-red-500', bg: 'bg-red-50 dark:bg-red-900/20', border: 'border-red-200 dark:border-red-800' },
  medium: { color: 'text-amber-500', bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-200 dark:border-amber-800' },
  low: { color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-900/20', border: 'border-blue-200 dark:border-blue-800' },
};

export default function AdversarialReviewCard({ result = {} }) {
  const [expanded, setExpanded] = useState(false);

  const counterArguments = result?.counterArguments ?? result?.counterArgs ?? [];
  const overallConfidence = result?.overallConfidence ?? result?.confidence;
  const adjustedConfidence = result?.adjustedConfidence ?? overallConfidence;
  const shouldSeek = result?.shouldSeekMoreEvidence ?? false;
  const hasAdjustment = overallConfidence != null && adjustedConfidence != null && overallConfidence !== adjustedConfidence;

  if (!counterArguments.length && overallConfidence == null) return null;

  return (
    <div className="adversarial-review-card rounded border border-pixiu-border overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-3 hover:bg-pixiu-surface/50 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <ShieldAlert size={16} className="text-red-500" />
          <span className="text-sm font-medium text-pixiu">
            对抗审查 · {counterArguments.length} 条反驳
          </span>
          {shouldSeek && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 font-medium">
              需要更多证据
            </span>
          )}
        </div>
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>

      {expanded && (
        <div className="p-3 space-y-3 border-t border-pixiu-border">
          {/* Confidence adjustment */}
          {hasAdjustment && (
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <div className="flex justify-between text-xs text-pixiu-muted mb-1">
                  <span>原始置信度</span>
                  <span className="font-mono">{(overallConfidence * 100).toFixed(0)}%</span>
                </div>
                <div className="w-full h-2 rounded-full bg-pixiu-surface">
                  <div className="h-2 rounded-full bg-green-400" style={{ width: `${Math.round(overallConfidence * 100)}%` }} />
                </div>
              </div>
              <TrendingDown size={16} className="text-red-400" />
              <div className="flex-1">
                <div className="flex justify-between text-xs text-pixiu-muted mb-1">
                  <span>调整后</span>
                  <span className="font-mono">{(adjustedConfidence * 100).toFixed(0)}%</span>
                </div>
                <div className="w-full h-2 rounded-full bg-pixiu-surface">
                  <div className="h-2 rounded-full bg-red-400" style={{ width: `${Math.round(adjustedConfidence * 100)}%` }} />
                </div>
              </div>
            </div>
          )}

          {/* Counter arguments */}
          {counterArguments.map((arg, i) => {
            const severity = arg.severity ?? 'medium';
            const config = SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG.medium;
            return (
              <div key={i} className={`p-2 rounded border ${config.border} ${config.bg}`}>
                <div className="flex items-start gap-2">
                  <AlertTriangle size={14} className={`${config.color} mt-0.5 shrink-0`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-semibold ${config.color}`}>{arg.aspect ?? `反驳 ${i + 1}`}</span>
                      <span className={`text-xs px-1 py-0 rounded ${config.bg} ${config.color}`}>
                        {severity.toUpperCase()}
                      </span>
                    </div>
                    <p className="text-xs text-pixiu mt-1">{arg.argument ?? arg.summary ?? ''}</p>
                    {arg.recommendation && (
                      <p className="text-xs text-pixiu-muted mt-1 flex items-center gap-1">
                        <Search size={12} />
                        {arg.recommendation}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          {shouldSeek && (
            <div className="p-2 rounded bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800 text-xs text-amber-700 dark:text-amber-400 flex items-center gap-2">
              <Search size={14} />
              <span>置信度降至 0.5 以下，建议补充更多证据后再做结论。</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
