import React from 'react';
import {
  BookOpen,
  CheckCircle2,
  Info,
  Moon,
  Sun,
  Upload,
} from 'lucide-react';

const Navbar = ({
  onFileUpload,
  isReady = true,
  onToggleLibrary,
  theme = 'light',
  onToggleTheme,
  currentFileName,
  onOpenAbout,
}) => {
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      onFileUpload(file);
    }
    event.target.value = '';
  };

  return (
    <header className="theme-header theme-border z-50 flex h-14 shrink-0 items-center justify-between border-b px-4">
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-lg bg-pixiu p-1 shadow-sm shadow-pixiu/30">
            <img src="/貔貅白.png" alt="Pixiu Logo" className="h-full w-full object-contain" />
          </div>
          <span className="theme-text-primary whitespace-nowrap text-sm font-bold tracking-tight sm:text-base">
            Pixiu Academic Assistant
          </span>
        </div>

        {currentFileName && (
          <div className="theme-border hidden min-w-0 max-w-[28rem] items-center gap-2 border-l pl-4 text-sm lg:flex">
            <span className="theme-text-muted shrink-0">当前论文</span>
            <span className="theme-text-primary truncate font-medium">{currentFileName}</span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onToggleLibrary}
          className="theme-button-secondary flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium"
        >
          <BookOpen size={16} />
          <span className="hidden sm:inline">论文库</span>
        </button>

        <div className="flex items-center gap-2 text-sm">
          <CheckCircle2 size={16} className={isReady ? 'text-emerald-400' : 'theme-text-muted'} />
          <span className={isReady ? 'text-emerald-500' : 'theme-text-muted'}>
            {isReady ? '服务正常' : '服务异常'}
          </span>
        </div>

        <label className="flex cursor-pointer items-center gap-2 rounded-md bg-pixiu px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-pixiu-dark">
          <Upload size={16} />
          <span className="hidden sm:inline">上传论文</span>
          <input type="file" className="hidden" accept=".pdf" onChange={handleFileChange} />
        </label>

        <button
          type="button"
          onClick={onToggleTheme}
          className="theme-button-secondary flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium"
          aria-label={theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'}
          title={theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        <button
          type="button"
          onClick={onOpenAbout}
          className="theme-button-secondary hidden items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium lg:flex"
          title="关于"
        >
          <Info size={16} />
          <span>关于</span>
        </button>
      </div>
    </header>
  );
};

export default Navbar;
