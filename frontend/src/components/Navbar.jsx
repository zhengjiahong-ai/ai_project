import React from 'react';
import { Upload, BookOpen, CheckCircle2, MessageSquare, BarChart3, Bookmark ,LayoutDashboard} from 'lucide-react';

const Navbar = ({ onFileUpload, isReady = true, activeTab, onTabChange, onToggleLibrary }) => {
  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) onFileUpload(file);
    e.target.value = '';
  };

  return (
    <header className="h-14 bg-white border-b px-6 flex items-center justify-between shadow-sm z-50">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-3">
          <div className="bg-pixiu p-1 rounded-lg w-9 h-9 flex items-center justify-center overflow-hidden">
            <img src="/貔貅白.png" alt="Pixiu Logo" className="w-full h-full object-contain" />
          </div>
          <span className="font-bold text-xl tracking-tight text-slate-800">Pixiu</span>
        </div>
        
        <button 
          onClick={onToggleLibrary}
          className="flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-pixiu transition-colors"
        >
          <BookOpen size={16} />
          论文库
        </button>
      </div>

      {/* 核心修改：Tab 切换按钮组增加“学术笔记” */}
      <div className="flex bg-slate-100 p-1 rounded-xl border">
        <button
          onClick={() => onTabChange('chat')}
          className={`flex items-center gap-2 px-4 py-1 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'chat' ? 'bg-white text-pixiu shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <MessageSquare size={16} /> AI 对话
        </button>
        <button
          onClick={() => onTabChange('analysis')}
          className={`flex items-center gap-2 px-4 py-1 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'analysis' ? 'bg-white text-pixiu shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <BarChart3 size={16} /> 批判性分析
        </button>
        {/* 新增：篇章解构按钮 */}
  <button
    onClick={() => onTabChange('deconstruct')}
    className={`flex items-center gap-2 px-4 py-1 rounded-lg text-sm font-medium transition-all ${
      activeTab === 'deconstruct' ? 'bg-white text-pixiu shadow-sm' : 'text-slate-500 hover:text-slate-700'
    }`}
  >
    <LayoutDashboard size={16} /> 篇章解构
  </button>
        {/* 新增按钮 */}
        <button
          onClick={() => onTabChange('notes')}
          className={`flex items-center gap-2 px-4 py-1 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'notes' ? 'bg-white text-pixiu shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <Bookmark size={16} /> 学术笔记
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm">
          <CheckCircle2 size={16} className={isReady ? 'text-green-500' : 'text-slate-400'} />
          <span className={isReady ? 'text-green-600' : 'text-slate-400'}>AI 就绪</span>
        </div>

        <label className="flex items-center gap-2 bg-pixiu hover:bg-pixiu-dark text-white px-4 py-1.5 rounded-lg transition shadow-sm font-medium cursor-pointer">
          <Upload size={16} /> 
          <span>上传论文</span>
          <input type="file" className="hidden" accept=".pdf" onChange={handleFileChange} />
        </label>
      </div>
    </header>
  );
};

export default Navbar;