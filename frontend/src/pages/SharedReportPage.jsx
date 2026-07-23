import React, { useEffect, useState } from 'react';
import { AlertTriangle, Shield } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8081/api';

/** Extract the share token from the URL path: /share/<token> */
function _tokenFromPath() {
  const match = window.location.pathname.match(/^\/share\/([a-f0-9]+)$/i);
  return match ? match[1] : '';
}

/**
 * SharedReportPage — read-only view of a shared agent project report (17-4).
 *
 * Route:  /share/:token
 * Fetches ``GET /api/shared/{token}`` and renders the report sections.
 * Shows an empty state when the token is invalid or expired.
 */
export default function SharedReportPage() {
  const token = _tokenFromPath();
  const [state, setState] = useState({ loading: true, error: '', data: null });

  useEffect(() => {
    let cancelled = false;
    async function fetchShare() {
      try {
        const resp = await fetch(`${API_BASE.replace(/\/$/, '')}/shared/${encodeURIComponent(token)}`);
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          throw new Error(body.message || '分享链接无效。');
        }
        const json = await resp.json();
        if (!cancelled) setState({ loading: false, error: '', data: json.share || json });
      } catch (err) {
        if (!cancelled) setState({ loading: false, error: err.message || '无法加载分享内容。', data: null });
      }
    }
    fetchShare();
    return () => { cancelled = true; };
  }, [token]);

  if (state.loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--bg-primary)]">
        <div className="text-center text-[color:var(--text-muted)]">加载中...</div>
      </div>
    );
  }

  if (state.error || !state.data) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--bg-primary)]">
        <div className="mx-auto max-w-md rounded-2xl border border-dashed border-[color:var(--border)] p-8 text-center">
          <AlertTriangle size={32} className="mx-auto mb-3 text-[color:var(--text-muted)]" />
          <h2 className="mb-2 text-lg font-semibold">链接已过期</h2>
          <p className="text-sm text-[color:var(--text-muted)]">{state.error || '该分享链接不存在或已过期。'}</p>
        </div>
      </div>
    );
  }

  const { report, projectTitle, expiresAt } = state.data;
  const sections = (report || '').split('\n').filter(Boolean);

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <header className="border-b border-[color:var(--border)] px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield size={16} className="text-[color:var(--text-muted)]" />
            <span className="text-xs font-semibold text-[color:var(--text-muted)]">分享视图 · 只读</span>
          </div>
          <div className="text-xs text-[color:var(--text-muted)]">
            {expiresAt ? `过期时间: ${new Date(expiresAt).toLocaleString()}` : ''}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-8">
        {projectTitle && (
          <h1 className="mb-6 text-xl font-bold">{projectTitle}</h1>
        )}
        <div className="space-y-2">
          {sections.map((line, idx) => (
            <div key={idx} className="whitespace-pre-wrap rounded-xl bg-[var(--bg-card)] px-4 py-2.5 text-sm leading-6">
              {line}
            </div>
          ))}
        </div>
        {sections.length === 0 && (
          <div className="rounded-2xl border border-dashed border-[color:var(--border)] p-6 text-center text-sm text-[color:var(--text-muted)]">
            此报告暂无内容。
          </div>
        )}
      </main>
    </div>
  );
}
