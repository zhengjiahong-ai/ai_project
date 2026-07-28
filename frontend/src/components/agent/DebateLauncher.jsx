import React, { useState, useCallback } from 'react';
import { MessageCircle, X, Loader2 } from 'lucide-react';
import { apiService } from '../../services/api.ts';

const DebateLauncher = ({
  activeProject,
  onDebateComplete,
  theme = 'light',
}) => {
  const [showDialog, setShowDialog] = useState(false);
  const [selectedPapers, setSelectedPapers] = useState([]);
  const [numAgents, setNumAgents] = useState(3);
  const [running, setRunning] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [error, setError] = useState('');

  const paperIds = activeProject?.paperIds || [];
  const canDebate = paperIds.length >= 2;

  const openDialog = useCallback(() => {
    setSelectedPapers([...paperIds]);
    setNumAgents(Math.min(3, paperIds.length));
    setError('');
    setShowDialog(true);
  }, [paperIds]);

  const togglePaper = useCallback((pdfId) => {
    setSelectedPapers((prev) =>
      prev.includes(pdfId) ? prev.filter((id) => id !== pdfId) : [...prev, pdfId]
    );
  }, []);

  const startDebate = useCallback(async () => {
    if (selectedPapers.length < 2) {
      setError('请至少选择 2 篇论文参与辩论。');
      return;
    }
    setRunning(true);
    setError('');
    setStatusText('正在启动多 Agent 辩论...');

    try {
      const response = await apiService.startAgentDebate(activeProject.id, {
        research_prompt: activeProject.title || '自动研究辩论',
        paper_ids: selectedPapers,
        num_agents: numAgents,
      });

      const runId = response?.data?.run_id || response?.run_id;
      if (!runId) {
        throw new Error('辩论启动失败：未返回 run_id');
      }

      setStatusText('辩论进行中，等待结果...');

      // Poll for results (max 60s)
      let result = null;
      for (let i = 0; i < 30; i++) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        try {
          const pollResponse = await apiService.getAgentDebateResult(activeProject.id, runId);
          result = pollResponse?.data || pollResponse;
          if (result?.status === 'completed') {
            break;
          }
        } catch {
          // Continue polling
        }
        setStatusText(`辩论第 ${Math.ceil((i + 1) / 3)} 轮...`);
      }

      if (result?.status === 'completed') {
        setStatusText('辩论完成！');
        if (onDebateComplete) {
          onDebateComplete(result);
        }
        setShowDialog(false);
      } else {
        setError('辩论超时，请稍后手动刷新查看结果。');
      }
    } catch (err) {
      setError(`辩论失败: ${err.message || err}`);
    } finally {
      setRunning(false);
    }
  }, [selectedPapers, numAgents, activeProject, onDebateComplete]);

  return (
    <>
      <button
        type="button"
        onClick={openDialog}
        disabled={!canDebate}
        title={canDebate ? '发起多 Agent 辩论' : '需要至少 2 篇论文才能发起辩论'}
        className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold transition ${
          canDebate
            ? 'agent-secondary-button cursor-pointer'
            : 'cursor-not-allowed opacity-40'
        }`}
      >
        <MessageCircle size={14} />
        发起辩论
      </button>

      {showDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => !running && setShowDialog(false)}>
          <div
            className={`w-full max-w-md rounded-2xl p-6 shadow-lg ${theme === 'dark' ? 'bg-gray-800 text-gray-100' : 'bg-white text-gray-900'}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">发起多 Agent 辩论</h3>
              <button
                type="button"
                onClick={() => !running && setShowDialog(false)}
                disabled={running}
                className="rounded-lg p-1 hover:bg-gray-200 dark:hover:bg-gray-700"
              >
                <X size={18} />
              </button>
            </div>

            {running ? (
              <div className="flex flex-col items-center gap-3 py-6">
                <Loader2 size={32} className="animate-spin text-blue-500" />
                <p className="text-sm">{statusText}</p>
              </div>
            ) : (
              <>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium">选择参与辩论的论文（至少 2 篇）：</label>
                  <div className="max-h-40 space-y-1 overflow-y-auto">
                    {paperIds.map((pdfId) => (
                      <label key={pdfId} className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedPapers.includes(pdfId)}
                          onChange={() => togglePaper(pdfId)}
                          className="rounded"
                        />
                        <span className="truncate">{pdfId}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium">Agent 数量：</label>
                  <select
                    value={numAgents}
                    onChange={(e) => setNumAgents(Number(e.target.value))}
                    className={`w-full rounded-xl border px-3 py-2 text-sm ${theme === 'dark' ? 'bg-gray-700 border-gray-600' : 'bg-gray-50 border-gray-200'}`}
                  >
                    {[2, 3, 4, 5].map((n) => (
                      <option key={n} value={n}>{n} 个 Agent</option>
                    ))}
                  </select>
                </div>

                {error && (
                  <p className="mb-3 text-sm text-red-500">{error}</p>
                )}

                <button
                  type="button"
                  onClick={startDebate}
                  disabled={selectedPapers.length < 2}
                  className="w-full rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-40"
                >
                  开始辩论
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default DebateLauncher;
