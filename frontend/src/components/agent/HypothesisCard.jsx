import { useState } from 'react';
import { ChevronDown, ChevronRight, Lightbulb, CheckCircle2, XCircle, HelpCircle, AlertTriangle } from 'lucide-react';

const VERDICT_CONFIG = {
  supported: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-50 dark:bg-green-900/20', label: '支持' },
  refuted: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-50 dark:bg-red-900/20', label: '否定' },
  inconclusive: { icon: HelpCircle, color: 'text-yellow-500', bg: 'bg-yellow-50 dark:bg-yellow-900/20', label: '不确定' },
  unverified: { icon: AlertTriangle, color: 'text-gray-400', bg: 'bg-gray-50 dark:bg-gray-800', label: '未验证' },
};

export default function HypothesisCard({ result = {} }) {
  const [expanded, setExpanded] = useState(false);
  const hypotheses = result?.hypotheses ?? [];

  if (!hypotheses.length) return null;

  return (
    <div className="hypothesis-card rounded border border-pixiu-border overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-3 hover:bg-pixiu-surface/50 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <Lightbulb size={16} className="text-yellow-500" />
          <span className="text-sm font-medium text-pixiu">
            研究假设 · {hypotheses.length} 条
          </span>
          <span className="text-xs text-pixiu-muted">
            (置信度: {result?.overallConfidence != null ? `${(result.overallConfidence * 100).toFixed(0)}%` : '—'})
          </span>
        </div>
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>

      {expanded && (
        <div className="p-3 space-y-2 border-t border-pixiu-border">
          {hypotheses.map((h, i) => {
            const verdict = h.verdict ?? h.status ?? 'unverified';
            const config = VERDICT_CONFIG[verdict] ?? VERDICT_CONFIG.unverified;
            const Icon = config.icon;

            return (
              <div key={i} className={`p-2 rounded ${config.bg} border border-pixiu-border`}>
                <div className="flex items-start gap-2">
                  <Icon size={16} className={`${config.color} mt-0.5 shrink-0`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-pixiu">{h.statement ?? h.hypothesis ?? ''}</p>
                    {h.testablePrediction && (
                      <p className="text-xs text-pixiu-muted mt-0.5">
                        预测: {h.testablePrediction}
                      </p>
                    )}
                    {h.requiredEvidenceType && (
                      <p className="text-xs text-pixiu-muted mt-0.5">
                        需要证据类型: {h.requiredEvidenceType}
                      </p>
                    )}
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-xs font-medium ${config.color}`}>
                        {config.label}
                      </span>
                      {h.confidence != null && (
                        <span className="text-xs text-pixiu-muted">
                          置信度: {(h.confidence * 100).toFixed(0)}%
                        </span>
                      )}
                      {h.evidenceCount != null && (
                        <span className="text-xs text-pixiu-muted">
                          证据: {h.evidenceCount} 条
                        </span>
                      )}
                    </div>
                    {h.reason && (
                      <p className="text-xs text-pixiu-muted mt-1">{h.reason}</p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
