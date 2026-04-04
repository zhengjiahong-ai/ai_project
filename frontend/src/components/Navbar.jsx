import React from 'react';
import {
  BarChart3,
  BookOpen,
  Bookmark,
  CheckCircle2,
  LayoutDashboard,
  MessageSquare,
  Sparkles,
  Upload,
} from 'lucide-react';

const Navbar = ({ onFileUpload, isReady = true, activeTab, onTabChange, onToggleLibrary }) => {
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      onFileUpload(file);
    }
    event.target.value = '';
  };

  return (
    <header className="z-50 flex h-14 items-center justify-between border-b bg-white px-6 shadow-sm">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-lg bg-pixiu p-1">
            <img src="/貔貅白.png" alt="Pixiu Logo" className="h-full w-full object-contain" />
          </div>
          <span className="text-xl font-bold tracking-tight text-slate-800">Pixiu</span>
        </div>

        <button
          onClick={onToggleLibrary}
          className="flex items-center gap-2 text-sm font-medium text-slate-600 transition-colors hover:text-pixiu"
        >
          <BookOpen size={16} />
          论文库
        </button>
      </div>

      <div className="flex rounded-xl border bg-slate-100 p-1">
        <button
          onClick={() => onTabChange('chat')}
          className={`flex items-center gap-2 rounded-lg px-4 py-1 text-sm font-medium transition-all ${
            activeTab === 'chat' ? 'bg-white text-pixiu shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <MessageSquare size={16} />
          AI 对话
        </button>
        <button
          onClick={() => onTabChange('analysis')}
          className={`flex items-center gap-2 rounded-lg px-4 py-1 text-sm font-medium transition-all ${
            activeTab === 'analysis' ? 'bg-white text-pixiu shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <BarChart3 size={16} />
          批判性分析
        </button>
        <button
          onClick={() => onTabChange('socratic')}
          className={`flex items-center gap-2 rounded-lg px-4 py-1 text-sm font-medium transition-all ${
            activeTab === 'socratic' ? 'bg-white text-pixiu shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <Sparkles size={16} />
          引导式学习
        </button>
        <button
          onClick={() => onTabChange('deconstruct')}
          className={`flex items-center gap-2 rounded-lg px-4 py-1 text-sm font-medium transition-all ${
            activeTab === 'deconstruct' ? 'bg-white text-pixiu shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <LayoutDashboard size={16} />
          篇章解构
        </button>
        <button
          onClick={() => onTabChange('notes')}
          className={`flex items-center gap-2 rounded-lg px-4 py-1 text-sm font-medium transition-all ${
            activeTab === 'notes' ? 'bg-white text-pixiu shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <Bookmark size={16} />
          学术笔记
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm">
          <CheckCircle2 size={16} className={isReady ? 'text-green-500' : 'text-slate-400'} />
          <span className={isReady ? 'text-green-600' : 'text-slate-400'}>AI 就绪</span>
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
