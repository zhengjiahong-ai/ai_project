import React from 'react';
import { Bell, BookOpen, CheckCircle2, Moon, Sun, Upload } from 'lucide-react';

const Navbar = ({ onFileUpload, isReady = true, onToggleLibrary, theme = 'light', onToggleTheme, appMode = 'reader', onAppModeChange }) => {
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) onFileUpload(file);
    event.target.value = '';
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
        <span className="pixiu-service-state" title={isReady ? '服务正常' : '服务异常'}><CheckCircle2 size={15} className={isReady ? 'text-emerald-500' : 'theme-text-muted'} /><span className="hidden 2xl:inline">{isReady ? '在线' : '异常'}</span></span>
        <button type="button" className="pixiu-icon-action" aria-label="通知"><Bell size={17} /></button>
        <button type="button" onClick={onToggleTheme} className="pixiu-icon-action" aria-label={theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'}>{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}</button>
      </div>
    </header>
  );
};

export default Navbar;
