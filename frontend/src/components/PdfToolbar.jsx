import { Sparkles, FileText, Languages, Zap, ShieldAlert } from 'lucide-react';

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
        className={`p-2.5 rounded-xl flex items-center gap-2 transition-all shadow-lg ${
          isTranslated ? 'bg-slate-800 text-white' : 'bg-pixiu text-white hover:bg-pixiu-dark'
        }`}
        title="动态解释模式"
      >
        <Zap size={18} />
        <span className="text-sm font-semibold">动态解释</span>
      </button>

      <button 
        onClick={onToggleTranslation}
        className={`text-xs flex items-center gap-1 font-semibold uppercase tracking-wider transition-all px-2 py-1 rounded-md ${
          isTranslated 
          ? 'bg-pixiu text-white shadow-md shadow-pixiu/20' 
          : 'text-slate-500 hover:text-pixiu'
        }`}
      >
        <Languages size={14} className={isTranslated ? 'text-white' : 'text-pixiu'}/>
        全景翻译
      </button>

      <div className="w-[1px] h-4 bg-slate-300"></div>

      <button 
        onClick={onCriticalReading}
        className="p-2.5 bg-white text-pixiu border-2 border-pixiu rounded-xl flex items-center gap-2 hover:bg-pixiu hover:text-white transition-all shadow-lg"
        title="批判性阅读"
      >
        <ShieldAlert size={18} />
        <span className="text-sm font-semibold">批判阅读</span>
      </button>

      <div className="w-[1px] h-4 bg-slate-300"></div>
      <button
        onClick={onSocraticLearning}
        className="text-xs flex items-center gap-1 hover:text-pixiu font-semibold uppercase tracking-wider text-slate-500 transition-colors"
      >
        <Sparkles size={14} className="text-pixiu" />
        引导式学习
      </button>
    </div>
  );
};

export default PdfToolbar;
