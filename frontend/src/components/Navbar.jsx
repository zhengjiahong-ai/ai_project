import React from 'react';
import {
  BarChart3,
  BookOpen,
  Bookmark,
  CheckCircle2,
  LayoutDashboard,
  MessageSquare,
  Moon,
  Sparkles,
  Sun,
  Upload,
} from 'lucide-react';

const navItems = [
  { id: 'chat', label: 'AI 对话', icon: MessageSquare },
  { id: 'analysis', label: '批判性分析', icon: BarChart3 },
  { id: 'socratic', label: '引导式学习', icon: Sparkles },
  { id: 'deconstruct', label: '篇章解构', icon: LayoutDashboard },
  { id: 'notes', label: '学术笔记', icon: Bookmark },
];

const Navbar = ({
  onFileUpload,
  isReady = true,
  activeTab,
  onTabChange,
  onToggleLibrary,
  theme = 'light',
  onToggleTheme,
}) => {
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      onFileUpload(file);
    }
    event.target.value = '';
  };

  return (
    <header className="theme-header theme-border z-50 flex h-14 items-center justify-between border-b px-6">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-lg bg-pixiu p-1 shadow-sm shadow-pixiu/30">
            <img src="/貔貅白.png" alt="Pixiu Logo" className="h-full w-full object-contain" />
          </div>
          <span className="theme-text-primary text-xl font-bold tracking-tight">Pixiu</span>
        </div>

        <button
          onClick={onToggleLibrary}
          className="theme-text-secondary flex items-center gap-2 text-sm font-medium transition-colors hover:text-pixiu"
        >
          <BookOpen size={16} />
          论文库
        </button>
      </div>

      <div className="theme-tab-group flex rounded-xl p-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`theme-tab flex items-center gap-2 rounded-lg px-4 py-1 text-sm font-medium transition-all ${
                isActive ? 'theme-tab-active' : ''
              }`}
            >
              <Icon size={16} />
              {item.label}
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onToggleTheme}
          className="theme-button-secondary flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium"
          aria-label={theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'}
          title={theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          <span>{theme === 'dark' ? '日间' : '夜间'}</span>
        </button>

        <div className="flex items-center gap-2 text-sm">
          <CheckCircle2 size={16} className={isReady ? 'text-emerald-400' : 'theme-text-muted'} />
          <span className={isReady ? 'text-emerald-500' : 'theme-text-muted'}>AI 就绪</span>
        </div>

        <label className="flex cursor-pointer items-center gap-2 rounded-lg bg-pixiu px-4 py-1.5 font-medium text-white shadow-sm transition hover:bg-pixiu-dark">
          <Upload size={16} />
          <span>上传论文</span>
          <input type="file" className="hidden" accept=".pdf" onChange={handleFileChange} />
        </label>
      </div>
    </header>
  );
};

export default Navbar;
