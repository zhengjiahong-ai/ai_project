import { useState } from 'react';
import { ChevronDown, ChevronRight, TrendingUp, Activity, Scale, AlertTriangle } from 'lucide-react';
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const GRADE_LABELS = { 4: 'High', 3: 'Moderate', 2: 'Low', 1: 'Very Low' };
const GRADE_COLORS = { 4: '#22c55e', 3: '#eab308', 2: '#f97316', 1: '#ef4444' };

export default function MetaAnalysisCard({ result = {} }) {
  const [expanded, setExpanded] = useState(false);

  const forestData = (result?.forestPlot ?? result?.forestData ?? []).map((d, i) => ({
    name: d.label ?? d.study ?? `Study ${i + 1}`,
    es: d.effectSize ?? d.es ?? 0,
    lower: d.ciLower ?? d.lower ?? 0,
    upper: d.ciUpper ?? d.upper ?? 0,
    weight: d.weight ?? 1,
  }));

  const heterogeneity = result?.heterogeneity ?? {};
  const grade = result?.grade ?? {};
  const egger = result?.eggerTest ?? result?.publicationBias ?? {};

  if (!result?.status && !result?.studyCount) return null;

  return (
    <div className="meta-analysis-card rounded border border-pixiu-border overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-3 hover:bg-pixiu-surface/50 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <TrendingUp size={16} className="text-pixiu-accent" />
          <span className="text-sm font-medium text-pixiu">
            元分析 · {result?.studyCount ?? 0} 项研究
          </span>
        </div>
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>

      {expanded && (
        <div className="p-3 space-y-3 border-t border-pixiu-border">
          {/* Stats row */}
          <div className="grid grid-cols-3 gap-2">
            <div className="p-2 rounded bg-pixiu-surface text-center">
              <div className="text-xs text-pixiu-muted">Q 统计量</div>
              <div className="text-sm font-mono font-semibold text-pixiu">
                {heterogeneity.qStatistic?.toFixed?.(2) ?? heterogeneity.Q ?? '—'}
              </div>
            </div>
            <div className="p-2 rounded bg-pixiu-surface text-center">
              <div className="text-xs text-pixiu-muted">I²</div>
              <div className="text-sm font-mono font-semibold text-pixiu">
                {heterogeneity.iSquared != null ? `${(heterogeneity.iSquared * 100).toFixed(0)}%` : '—'}
              </div>
            </div>
            <div className="p-2 rounded bg-pixiu-surface text-center">
              <div className="text-xs text-pixiu-muted">τ²</div>
              <div className="text-sm font-mono font-semibold text-pixiu">
                {heterogeneity.tauSquared?.toFixed?.(3) ?? heterogeneity.tau2 ?? '—'}
              </div>
            </div>
          </div>

          {/* GRADE badge */}
          {grade.level && (
            <div className="flex items-center gap-2 p-2 rounded text-xs"
              style={{ backgroundColor: `${GRADE_COLORS[grade.level] ?? 'var(--text-muted)'}20` }}>
              <Scale size={14} style={{ color: GRADE_COLORS[grade.level] ?? 'var(--text-muted)' }} />
              <span className="font-medium" style={{ color: GRADE_COLORS[grade.level] ?? 'var(--text-muted)' }}>
                GRADE: {GRADE_LABELS[grade.level] ?? grade.level}
              </span>
              {grade.reason && <span className="text-pixiu-muted">— {grade.reason}</span>}
            </div>
          )}

          {/* Publication bias */}
          {egger.pValue != null && (
            <div className="flex items-center gap-2 text-xs">
              <AlertTriangle size={14} className={egger.pValue < 0.05 ? 'text-yellow-500' : 'text-green-500'} />
              <span className="text-pixiu-muted">
                Egger's test: p = {typeof egger.pValue === 'number' ? egger.pValue.toFixed(3) : egger.pValue}
                {egger.pValue < 0.05 ? ' — 可能存在发表偏倚' : ' — 未检测到显著发表偏倚'}
              </span>
            </div>
          )}

          {/* Forest plot */}
          {forestData.length > 0 && (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis type="number" dataKey="es" tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={80} />
                  <ZAxis type="number" dataKey="weight" range={[20, 120]} />
                  <Tooltip
                    formatter={(value, name) => [typeof value === 'number' ? value.toFixed(3) : value, name === 'es' ? 'Effect Size' : name]}
                    contentStyle={{ fontSize: 12 }}
                  />
                  <Scatter data={forestData} shape="diamond">
                    {forestData.map((entry, i) => (
                      <Cell key={i} fill={entry.es > 0 ? '#22c55e' : '#ef4444'} opacity={0.7} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Combined effect */}
          {result?.combinedEffect && (
            <div className="flex items-center gap-2 text-xs">
              <Activity size={14} className="text-pixiu-accent" />
              <span className="text-pixiu-muted">
                合并效应量: {typeof result.combinedEffect === 'number' ? result.combinedEffect.toFixed(3) : result.combinedEffect}
                {result?.combinedCI && ` [${result.combinedCI[0]?.toFixed?.(3) ?? result.combinedCI[0]}, ${result.combinedCI[1]?.toFixed?.(3) ?? result.combinedCI[1]}]`}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
