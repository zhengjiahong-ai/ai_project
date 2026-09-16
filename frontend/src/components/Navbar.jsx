import React, { useEffect, useRef, useState } from 'react';
import { Activity, BookOpen, CheckCircle2, Loader2, Moon, Sun, Upload, X } from 'lucide-react';

const DEFAULT_MODEL_NAME = 'DeepSeek V4';
const DEFAULT_API_BASE_URL = 'http://localhost:8081/api';
const DEFAULT_PYTHON_DIRECT_URL = 'http://localhost:8000';

const Navbar = ({ onFileUpload, isReady = true, onToggleLibrary, theme = 'light', onToggleTheme, appMode = 'reader', onAppModeChange }) => {
  const [isStatusOpen, setIsStatusOpen] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const statusPanelRef = useRef(null);

  const env = typeof import.meta !== 'undefined' ? import.meta.env : undefined;
  const modelName = env?.VITE_MODEL_NAME || DEFAULT_MODEL_NAME;
  const apiBaseUrl = env?.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;
  const pythonDirectUrl = env?.VITE_PYTHON_DIRECT_URL || DEFAULT_PYTHON_DIRECT_URL;

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) onFileUpload(file);
    event.target.value = '';
  };

  useEffect(() => {
    if (!isStatusOpen) return undefined;
    const handleClickOutside = (event) => {
      if (statusPanelRef.current && !statusPanelRef.current.contains(event.target)) {
        setIsStatusOpen(false);
      }
    };
    const handleEsc = (event) => {
      if (event.key === 'Escape') setIsStatusOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [isStatusOpen]);

  const probeEndpoint = async (endpoint) => {
    const startedAt = Date.now();
    try {
      const resp = await fetch(endpoint, { method: 'GET' });
      const latency = Date.now() - startedAt;
      if (!resp.ok) {
        return { ok: false, latency, endpoint, error: `HTTP ${resp.status}` };
      }
      const data = await resp.json();
      return { ok: true, latency, endpoint, data };
    } catch (err) {
      return { ok: false, latency: Date.now() - startedAt, endpoint, error: err?.message || '网络错误' };
    }
  };

  const handleTestConnectivity = async () => {
    setIsTesting(true);
    setTestResult(null);
    const gatewayEndpoint = `${apiBaseUrl.replace(/\/$/, '')}/health`;
    const directEndpoint = `${pythonDirectUrl.replace(/\/$/, '')}/health`;

    // 优先试网关（生产环境统一入口），失败则 fallback 直连 Python（开发环境）
    let probe = await probeEndpoint(gatewayEndpoint);
    let usedFallback = false;
    let gatewayError = null;
    if (!probe.ok) {
      gatewayError = probe.error;
      const fallback = await probeEndpoint(directEndpoint);
      if (fallback.ok) {
        probe = fallback;
        usedFallback = true;
      } else {
        setTestResult({
          ok: false,
          status: 'unreachable',
          latency: probe.latency + fallback.latency,
          checks: {},
          uptime: null,
          message: '两个端点均不可达',
          gatewayEndpoint,
          directEndpoint,
          gatewayError,
          directError: fallback.error,
          usedFallback: false,
        });
        setIsTesting(false);
        return;
      }
    }

    const data = probe.data || {};
    const aggregate = data.status || 'unknown';
    setTestResult({
      ok: aggregate === 'ok',
      status: aggregate,
      latency: probe.latency,
      checks: data.checks || {},
      uptime: typeof data.uptime_seconds === 'number' ? data.uptime_seconds : null,
      message: aggregate === 'ok' ? '连接正常' : aggregate === 'degraded' ? '服务降级' : '未知状态',
      gatewayEndpoint,
      directEndpoint,
      gatewayError,
      usedFallback,
      resolvedEndpoint: probe.endpoint,
    });
    setIsTesting(false);
  };

  return (
    <header className="pixiu-topbar theme-header theme-border z-50 grid h-16 shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b px-6">
      <div className="flex min-w-0 items-center gap-3">
        <img src="/貔貅紫白.png" alt="Pixiu Logo" className="h-10 w-10 shrink-0 object-contain" />
        <span className="pixiu-brand theme-text-primary truncate text-lg font-bold tracking-tight">Pixiu Academic Assistant</span>
      </div>
      <nav className="pixiu-mode-switch flex h-10 items-stretch" aria-label="工作区切换">
        <button type="button" onClick={() => onAppModeChange?.('reader')} className={`pixiu-mode-tab ${appMode === 'reader' ? 'pixiu-mode-tab-active' : ''}`}>阅读 IDE</button>
        <button type="button" onClick={() => onAppModeChange?.('agent')} className={`pixiu-mode-tab ${appMode === 'agent' ? 'pixiu-mode-tab-active' : ''}`}>研究 Agent</button>
      </nav>
      <div className="flex items-center justify-end gap-1.5">
        <button onClick={onToggleLibrary} className="pixiu-nav-action"><BookOpen size={17} /><span className="hidden xl:inline">论文库</span></button>
        <label className="pixiu-nav-action cursor-pointer"><Upload size={17} /><span className="hidden xl:inline">上传论文</span><input type="file" className="hidden" accept=".pdf" onChange={handleFileChange} /></label>
        <span className="theme-border mx-1 h-6 border-l" />
        <div className="pixiu-status-anchor" ref={statusPanelRef}>
          <button
            type="button"
            onClick={() => setIsStatusOpen((prev) => !prev)}
            className="pixiu-service-state pixiu-service-state-button"
            title="点击查看服务详情"
            aria-expanded={isStatusOpen}
            aria-haspopup="dialog"
          >
            <CheckCircle2 size={15} className={isReady ? 'text-emerald-500' : 'theme-text-muted'} />
            <span className="hidden 2xl:inline">{isReady ? '在线' : '异常'}</span>
          </button>
          {isStatusOpen && (
            <div className="pixiu-status-popover theme-panel theme-border" role="dialog" aria-label="服务状态详情">
              <div className="pixiu-status-popover-header">
                <span className="pixiu-status-popover-title">服务状态</span>
                <button
                  type="button"
                  className="pixiu-icon-action pixiu-status-close"
                  onClick={() => setIsStatusOpen(false)}
                  aria-label="关闭"
                >
                  <X size={14} />
                </button>
              </div>
              <div className="pixiu-status-popover-body">
                <div className="pixiu-status-row">
                  <span className="pixiu-status-label">当前模型</span>
                  <span className="pixiu-status-value">{modelName}</span>
                </div>
                <div className="pixiu-status-row">
                  <span className="pixiu-status-label">连接状态</span>
                  <span className="pixiu-status-value">
                    <span className={`pixiu-status-badge ${isReady ? 'ok' : 'error'}`}>
                      {isReady ? '在线' : '异常'}
                    </span>
                    <button
                      type="button"
                      onClick={handleTestConnectivity}
                      disabled={isTesting}
                      className="pixiu-status-test-button"
                    >
                      {isTesting ? <Loader2 size={12} className="animate-spin" /> : <Activity size={12} />}
                      <span>{isTesting ? '测试中...' : '测试连通性'}</span>
                    </button>
                  </span>
                </div>
                {testResult && (
                  <div className={`pixiu-status-test-result ${testResult.ok ? 'ok' : 'error'}`}>
                    <div className="pixiu-status-test-summary">
                      <span>{testResult.ok ? '✓' : '✗'} {testResult.message}</span>
                      {typeof testResult.latency === 'number' && (
                        <span className="pixiu-status-latency">{testResult.latency} ms</span>
                      )}
                    </div>
                    {testResult.usedFallback && (
                      <div className="pixiu-status-fallback-note">
                        ⚠ 网关不可达（{testResult.gatewayError}），已直连 Python 服务
                      </div>
                    )}
                    {testResult.checks && Object.keys(testResult.checks).length > 0 && (
                      <ul className="pixiu-status-check-list">
                        {Object.entries(testResult.checks).map(([name, info]) => (
                          <li key={name}>
                            <span className={`pixiu-status-dot ${info?.status || 'unknown'}`}></span>
                            <span className="pixiu-status-check-name">{name}</span>
                            <span className="pixiu-status-check-msg">{info?.message || info?.status || '—'}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {typeof testResult.uptime === 'number' && (
                      <div className="pixiu-status-uptime">服务已运行 {Math.round(testResult.uptime)} 秒</div>
                    )}
                    {!testResult.ok && testResult.status === 'unreachable' && testResult.directError && (
                      <div className="pixiu-status-error-detail">
                        <div>网关：{testResult.gatewayError}</div>
                        <div>直连：{testResult.directError}</div>
                      </div>
                    )}
                    {testResult.resolvedEndpoint && (
                      <div className="pixiu-status-resolved-endpoint" title={testResult.resolvedEndpoint}>
                        → {testResult.resolvedEndpoint}
                      </div>
                    )}
                  </div>
                )}
                <div className="pixiu-status-endpoint">
                  <span className="pixiu-status-label">API 端点</span>
                  <code className="pixiu-status-endpoint-url" title={apiBaseUrl}>{apiBaseUrl}</code>
                </div>
              </div>
            </div>
          )}
        </div>
        <button type="button" onClick={onToggleTheme} className="pixiu-icon-action" aria-label={theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'}>{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}</button>
      </div>
    </header>
  );
};

export default Navbar;
