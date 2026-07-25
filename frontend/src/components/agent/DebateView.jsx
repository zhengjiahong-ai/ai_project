import { useState } from 'react';
import {
  Users, MessageSquare, CheckCircle, AlertTriangle,
  HelpCircle, ChevronDown, ChevronRight, Zap,
} from 'lucide-react';

/**
 * DebateView – Multi-agent debate visualization.
 *
 * Displays agent stance cards, evidence alignment matrix,
 * and consensus / dissent / unresolved result sections.
 */
export default function DebateView({ debateResult, theme = 'light' }) {
  const [expandedAgent, setExpandedAgent] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  if (!debateResult || !debateResult.agent_analyses) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center text-gray-400">
        <Users className="mb-3" size={40} />
        <p className="text-sm">No debate data available</p>
      </div>
    );
  }

  const {
    agent_analyses: analyses = [],
    debate_turns: turns = [],
    consensus_findings: consensus = [],
    minority_dissent: dissent = [],
    unresolved = [],
    jaccard_matrix: matrix = [],
    rounds = 0,
    duration_seconds: duration = 0,
  } = debateResult;

  const totalFindings = consensus.length + dissent.length + unresolved.length;
  const consensusRate = totalFindings > 0
    ? Math.round((consensus.length / totalFindings) * 100) : 0;

  const isDark = theme === 'dark';

  return (
    <div className="debate-view space-y-4 rounded-[22px] border border-gray-200 p-4 dark:border-gray-700">
      {/* Summary Bar */}
      <div className={`flex flex-wrap items-center gap-4 rounded-lg p-3 text-sm ${
        isDark ? 'bg-gray-800 text-gray-200' : 'bg-gray-50 text-gray-700'
      }`}>
        <span className="flex items-center gap-1"><Users size={16} /><strong>{analyses.length}</strong> Agents</span>
        <span className="flex items-center gap-1"><MessageSquare size={16} /><strong>{rounds}</strong> Rounds</span>
        <span className="flex items-center gap-1"><CheckCircle size={16} className="text-green-500" /><strong>{consensusRate}%</strong> consensus</span>
        <span className="flex items-center gap-1"><Zap size={16} />{duration.toFixed(1)}s</span>
        <div className="ml-auto h-2 w-32 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
          <div className="h-full rounded-full bg-green-500 transition-all" style={{ width: `${consensusRate}%` }} />
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 border-b border-gray-200 pb-1 dark:border-gray-700">
        {[
          { key: 'overview', label: 'Overview' },
          { key: 'results', label: 'Results' },
          { key: 'debate', label: 'Debate Log' },
        ].map((t) => (
          <button key={t.key} onClick={() => setActiveTab(t.key)}
            className={`rounded-t px-3 py-1.5 text-sm font-medium transition ${
              activeTab === t.key
                ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-4">
          {/* Stance Cards */}
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {analyses.map((analysis) => {
              const idx = analysis.agent_index;
              const findings = analysis.findings || [];
              const topFindings = findings.slice(0, 3);
              return (
                <div key={idx} className={`rounded-lg border p-3 transition ${
                  isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-white'
                }`}>
                  <div className="mb-2 flex items-center justify-between">
                    <h4 className="font-semibold text-sm">
                      Agent {String.fromCharCode(65 + idx)}{' '}
                      <span className="font-normal text-gray-400">(T={analysis.temperature})</span>
                    </h4>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      (analysis.credibility_mean || 0) >= 0.7
                        ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                        : (analysis.credibility_mean || 0) >= 0.4
                          ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400'
                          : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                    }`}>cred: {(analysis.credibility_mean || 0).toFixed(2)}</span>
                  </div>
                  <ul className="space-y-1 text-xs text-gray-600 dark:text-gray-400">
                    {topFindings.map((f, fi) => (
                      <li key={fi} className="line-clamp-2">• {(f.summary || '').slice(0, 120)}</li>
                    ))}
                    {findings.length === 0 && <li className="italic text-gray-400">No findings</li>}
                  </ul>
                  {findings.length > 3 && (
                    <button onClick={() => setExpandedAgent(expandedAgent === idx ? null : idx)}
                      className="mt-2 flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400">
                      {expandedAgent === idx ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      {findings.length - 3} more findings
                    </button>
                  )}
                  {expandedAgent === idx && (
                    <ul className="mt-2 space-y-1 border-t pt-2 text-xs text-gray-600 dark:border-gray-700 dark:text-gray-400">
                      {findings.slice(3).map((f, fi) => (
                        <li key={fi} className="line-clamp-2">• {(f.summary || '').slice(0, 120)}</li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>

          {/* Alignment Matrix */}
          {matrix.length > 1 && (
            <div className={`overflow-x-auto rounded-lg border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <h4 className="px-3 pt-3 text-sm font-semibold">Evidence Alignment Matrix</h4>
              <table className="w-full text-xs">
                <thead><tr className={isDark ? 'bg-gray-800' : 'bg-gray-50'}>
                  <th className="px-3 py-2 text-left">Finding</th>
                  {analyses.map((a) => (
                    <th key={a.agent_index} className="px-2 py-2 text-center">Agent {String.fromCharCode(65 + a.agent_index)}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {analyses.flatMap((a) => (a.findings || []).slice(0, 3)).filter((f, i, arr) =>
                    arr.findIndex((x) => x.finding_id === f.finding_id) === i
                  ).slice(0, 8).map((f) => (
                    <tr key={f.finding_id} className="border-t dark:border-gray-700">
                      <td className="max-w-[200px] truncate px-3 py-2">{(f.summary || '').slice(0, 80)}</td>
                      {analyses.map((a) => {
                        const af = (a.findings || []).find((af) => af.finding_id === f.finding_id);
                        if (!af) return <td key={a.agent_index} className="px-2 py-2 text-center text-gray-300">−</td>;
                        const cred = af.credibility || 0;
                        const symbol = cred >= 0.7 ? '✓' : cred < 0.4 ? '✗' : '~';
                        const bg = cred >= 0.7 ? 'bg-green-100 dark:bg-green-900/40'
                          : cred < 0.4 ? 'bg-red-100 dark:bg-red-900/40'
                          : 'bg-amber-100 dark:bg-amber-900/40';
                        return <td key={a.agent_index} className={`px-2 py-2 text-center font-medium ${bg}`}>{symbol}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'results' && (
        <div className="space-y-4">
          {/* Consensus */}
          <div className={`rounded-lg border p-4 ${isDark ? 'bg-green-900/20 border-gray-700' : 'bg-green-50 border-gray-200'}`}>
            <h4 className="mb-2 flex items-center gap-2 font-semibold text-green-800 dark:text-green-400">
              <CheckCircle size={18} /> Consensus Findings ({consensus.length})
            </h4>
            {consensus.length === 0 ? <p className="text-sm text-gray-500">No consensus findings</p> : (
              <ul className="space-y-2">
                {consensus.map((f, i) => (
                  <li key={i} className="text-sm">
                    <p>{f.summary}</p>
                    <span className="text-xs text-gray-500">
                      confidence: {f.confidence?.toFixed(2)} | agents: {f.supporting_agents?.join(', ')} | sources: {f.source_ids?.join(', ')}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {/* Minority Dissent */}
          <div className={`rounded-lg border p-4 ${isDark ? 'bg-amber-900/20 border-gray-700' : 'bg-amber-50 border-gray-200'}`}>
            <h4 className="mb-2 flex items-center gap-2 font-semibold text-amber-800 dark:text-amber-400">
              <AlertTriangle size={18} /> Minority Dissent ({dissent.length})
            </h4>
            {dissent.length === 0 ? <p className="text-sm text-gray-500">No dissenting findings</p> : (
              <ul className="space-y-2">
                {dissent.map((d, i) => (
                  <li key={i} className="text-sm">
                    <p><strong>Agent {String.fromCharCode(65 + (d.agent_index || 0))}:</strong> {d.summary}</p>
                    <p className="text-xs text-gray-500">{d.reason}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {/* Unresolved */}
          <div className={`rounded-lg border p-4 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-gray-100 border-gray-200'}`}>
            <h4 className="mb-2 flex items-center gap-2 font-semibold text-gray-600 dark:text-gray-400">
              <HelpCircle size={18} /> Unresolved ({unresolved.length})
            </h4>
            {unresolved.length === 0 ? <p className="text-sm text-gray-500">No unresolved conflicts</p> : (
              <ul className="space-y-2">
                {unresolved.map((u, i) => (
                  <li key={i} className="text-sm">
                    <p className="font-medium">{u.topic}</p>
                    <ul className="ml-4 mt-1 space-y-1">
                      {(u.positions || []).map((p, pi) => (
                        <li key={pi} className="text-xs text-gray-500">
                          Agent {String.fromCharCode(65 + (p.agent_index || 0))}: {p.summary?.slice(0, 100)}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {activeTab === 'debate' && (
        <div className="space-y-4">
          {!turns || turns.length === 0 ? (
            <p className="p-4 text-sm text-gray-500">No debate rounds recorded (single-agent analysis)</p>
          ) : (
            Object.entries(turns.reduce((acc, t) => {
              const r = t.round_index ?? 0;
              if (!acc[r]) acc[r] = [];
              acc[r].push(t);
              return acc;
            }, {})).map(([roundIdx, roundTurns]) => (
              <div key={roundIdx} className={`rounded-lg border p-4 ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                <h4 className="mb-3 font-semibold text-sm">Round {parseInt(roundIdx) + 1}</h4>
                {roundTurns.map((turn) => (
                  <div key={turn.agent_index} className={`mb-3 rounded p-3 text-xs ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                    <p className="mb-1 font-medium">Agent {String.fromCharCode(65 + turn.agent_index)}</p>
                    {(turn.rebuttals || []).slice(0, 3).map((r, ri) => (
                      <div key={ri} className="ml-2 border-l-2 border-red-400 pl-2 mb-1">
                        <span className="text-red-600 dark:text-red-400">Rebuttal re: Agent {String.fromCharCode(65 + r.from_agent)}</span>
                        : {r.summary?.slice(0, 100)}
                      </div>
                    ))}
                    {(turn.supplements || []).slice(0, 3).map((s, si) => (
                      <div key={si} className="ml-2 border-l-2 border-green-400 pl-2 mb-1">
                        <span className="text-green-600 dark:text-green-400">Support from Agent {String.fromCharCode(65 + s.from_agent)}</span>
                        : {s.summary?.slice(0, 100)}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
