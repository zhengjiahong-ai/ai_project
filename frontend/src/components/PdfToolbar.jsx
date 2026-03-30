import React from 'react';
import { Sparkles, FileText, Languages } from 'lucide-react';

/**
 * PDF 工具栏组件（悬浮在 PDF 视窗底部）
 * @param {Function} onDynamicExplain - 动态解释回调
 * @param {Function} onCriticalReading - 批判性阅读回调
 */
const PdfToolbar = ({ onDynamicExplain, onCriticalReading, onSocraticLearning, isTranslated, onToggleTranslation }) => {
  return (
    <div className="absolute bottom-10 left-1/2 -translate-x-1/2 bg-white/90 backdrop-blur shadow-xl border px-4 py-2 rounded-full flex items-center gap-4 z-20">
      <button 
        onClick={onDynamicExplain}
        className="text-xs flex items-center gap-1 hover:text-blue-600 font-semibold uppercase tracking-wider text-slate-500 transition-colors"
      >
        <Sparkles size={14} className="text-blue-500"/> 
        动态解释
      </button>
      {/* 🚀 新增：全景翻译按钮 */}
      <button 
        onClick={onToggleTranslation}
        className={`text-xs flex items-center gap-1 font-semibold uppercase tracking-wider transition-all px-2 py-1 rounded-md ${
          isTranslated 
          ? 'bg-blue-600 text-white shadow-md shadow-blue-200' 
          : 'text-slate-500 hover:text-blue-600'
        }`}
      >
        <Languages size={14} className={isTranslated ? 'text-white' : 'text-blue-500'}/>
        全景翻译
      </button>
      <div className="w-[1px] h-4 bg-slate-300"></div>
      <button 
        onClick={onCriticalReading}
        className="text-xs flex items-center gap-1 hover:text-blue-600 font-semibold uppercase tracking-wider text-slate-500 transition-colors"
      >
        <FileText size={14} className="text-blue-500"/>
        批判性阅读
      </button>

      <div className="w-[1px] h-4 bg-slate-300"></div>
      <button
        onClick={onSocraticLearning}
        className="text-xs flex items-center gap-1 hover:text-blue-600 font-semibold uppercase tracking-wider text-slate-500 transition-colors"
      >
        <Sparkles size={14} className="text-blue-500" />
        引导式学习
      </button>
    </div>
  );
};

export default PdfToolbar;
