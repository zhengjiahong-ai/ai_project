import React from 'react';
import { Upload, BookOpen, CheckCircle2 } from 'lucide-react';

/**
 * 顶部导航栏组件
 * @param {Function} onFileUpload - 文件上传回调函数
 * @param {boolean} isReady - AI 是否就绪
 */
const Navbar = ({ onFileUpload, isReady = true }) => {
  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      onFileUpload(file);
    }
    // 重置 input，允许重复选择同一文件
    e.target.value = '';
  };

  return (
    <header className="h-14 bg-white border-b px-6 flex items-center justify-between shadow-sm z-10">
      <div className="flex items-center gap-3">
        <div className="bg-blue-600 p-1.5 rounded-lg">
          <BookOpen size={20} className="text-white" />
        </div>
        <span className="font-bold text-lg tracking-tight">
          Scholar<span className="text-blue-600">Next</span>
        </span>
        <div className="ml-4 h-6 w-[1px] bg-slate-200"></div>
        <span className="text-sm text-slate-500 font-medium">2026 大创项目演示版</span>
      </div>

      <div className="flex items-center gap-4">
        {/* AI 状态指示 */}
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <CheckCircle2 
            size={16} 
            className={isReady ? 'text-green-500' : 'text-slate-400'} 
          />
          <span className={isReady ? 'text-green-600' : 'text-slate-400'}>
            {isReady ? 'AI 已就绪' : 'AI 连接中...'}
          </span>
        </div>

        {/* 上传按钮 */}
        <label className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded-lg transition shadow-sm font-medium cursor-pointer">
          <Upload size={16} /> 
          <span>上传论文</span>
          <input 
            type="file" 
            className="hidden" 
            accept=".pdf" 
            onChange={handleFileChange} 
          />
        </label>
      </div>
    </header>
  );
};

export default Navbar;
