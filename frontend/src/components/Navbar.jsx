import React from 'react';
import { Upload, BookOpen, CheckCircle2, MessageSquare, BarChart3 } from 'lucide-react';

const Navbar = ({ onFileUpload, isReady = true, activeTab, onTabChange }) => {
  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) onFileUpload(file);
    e.target.value = '';
  };

  return (
    <header className="h-14 bg-white border-b px-6 flex items-center justify-between shadow-sm z-50">
      <div className="flex items-center gap-3">
        <div className="bg-blue-600 p-1.5 rounded-lg">
          <BookOpen size={20} className="text-white" />
        </div>
        <span className="font-bold text-lg tracking-tight">Pixiu</span>
      </div>

      {/* 新增：Tab 切换按钮组 */}
      <div className="flex bg-slate-100 p-1 rounded-xl border">
        <button
          onClick={() => onTabChange('chat')}
          className={`flex items-center gap-2 px-4 py-1 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'chat' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <MessageSquare size={16} /> AI 对话
        </button>
        <button
          onClick={() => onTabChange('analysis')}
          className={`flex items-center gap-2 px-4 py-1 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'analysis' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <BarChart3 size={16} /> 批判性分析
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm">
          <CheckCircle2 size={16} className={isReady ? 'text-green-500' : 'text-slate-400'} />
          <span className={isReady ? 'text-green-600' : 'text-slate-400'}>AI 就绪</span>
        </div>

        <label className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded-lg transition shadow-sm font-medium cursor-pointer">
          <Upload size={16} /> 
          <span>上传论文</span>
          <input type="file" className="hidden" accept=".pdf" onChange={handleFileChange} />
        </label>
      </div>
    </header>
  );
};

export default Navbar;