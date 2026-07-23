import React from 'react';
import {
  BarChart, Bar, LineChart, Line, ScatterChart, Scatter,
  PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts';

const CHART_COLORS = [
  'var(--accent, #6366f1)',
  'var(--accent-strong, #4f46e5)',
  'var(--success, #16a34a)',
  'var(--warning, #ca8a04)',
  'var(--caution, #d97706)',
  'var(--info, #0ea5e9)',
];

/**
 * ChartAnalysisCard — renders structured chart data from VLM analysis (17-3).
 *
 * Props:
 *   evidence: { metadata: { chartData: { chartType, title, xAxis, yAxis, dataSeries, legend, caption, summary } } }
 */
export default function ChartAnalysisCard({ evidence }) {
  const chartData = evidence?.metadata?.chartData;
  if (!chartData || !chartData.chartType) {
    return (
      <div className="agent-card rounded-2xl px-3 py-2.5 text-xs text-[color:var(--text-muted)]">
        [图表数据不可用]
      </div>
    );
  }

  const { chartType, title, xAxis, yAxis, dataSeries, legend, caption, summary } = chartData;

  // Build data array for recharts from the first data series.
  const series = (dataSeries && dataSeries.length > 0) ? dataSeries[0] : null;
  const points = series?.dataPoints || [];
  const chartDataRows = points.map((pt, i) => ({
    name: xAxis?.values?.[i] ?? pt.x ?? `#${i + 1}`,
    value: pt.y ?? 0,
    error: pt.yError ?? null,
  }));

  const renderChart = () => {
    switch (chartType) {
      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartDataRows}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #e5e7eb)" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="var(--text-muted, #6b7280)" />
              <YAxis tick={{ fontSize: 10 }} stroke="var(--text-muted, #6b7280)" />
              <Tooltip />
              <Bar dataKey="value" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        );
      case 'line':
        return (
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={chartDataRows}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #e5e7eb)" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="var(--text-muted, #6b7280)" />
              <YAxis tick={{ fontSize: 10 }} stroke="var(--text-muted, #6b7280)" />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke={CHART_COLORS[0]} strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        );
      case 'scatter':
        return (
          <ResponsiveContainer width="100%" height={180}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #e5e7eb)" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="var(--text-muted, #6b7280)" />
              <YAxis tick={{ fontSize: 10 }} stroke="var(--text-muted, #6b7280)" />
              <Tooltip />
              <Scatter data={chartDataRows} fill={CHART_COLORS[0]} />
            </ScatterChart>
          </ResponsiveContainer>
        );
      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie
                data={chartDataRows}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={70}
                label={({ name, value }) => `${name}: ${value}`}
              >
                {chartDataRows.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        );
      default:
        return (
          <div className="text-[11px] text-[color:var(--text-muted)] py-3 text-center">
            图表类型 "{chartType}" 暂不支持可视化渲染，请查看原始数据。
          </div>
        );
    }
  };

  return (
    <div className="chart-analysis-card rounded-2xl border border-[color:var(--border)] bg-[var(--bg-card)] p-3">
      {title && <div className="mb-1 text-xs font-semibold">{title}</div>}
      {renderChart()}
      {(legend && legend.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-2">
          {legend.map((item, i) => (
            <span key={i} className="inline-flex items-center gap-1 text-[10px] text-[color:var(--text-muted)]">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}
              />
              {item.label || item.name || ''}
            </span>
          ))}
        </div>
      )}
      {caption && <div className="mt-1 text-[10px] text-[color:var(--text-muted)] italic">{caption}</div>}
      {summary && <div className="mt-1 text-[11px] text-[color:var(--text-secondary)]">{summary}</div>}
      {xAxis?.label && (
        <div className="mt-1 text-[10px] text-[color:var(--text-muted)]">
          X: {xAxis.label}{xAxis.unit ? ` (${xAxis.unit})` : ''} · Y: {yAxis?.label || ''}{yAxis?.unit ? ` (${yAxis.unit})` : ''}
        </div>
      )}
    </div>
  );
}
