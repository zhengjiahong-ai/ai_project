import { Sparkles, FileText, Languages, Zap, ShieldAlert } from 'lucide-react';

/**
 * PDF 工具栏组件（悬浮在 PDF 视窗底部）
 * @param {Function} onDynamicExplain - 动态解释回调
 * @param {Function} onCriticalReading - 批判性阅读回调
 */
const PdfToolbar = ({ onDynamicExplain, onCriticalReading, onSocraticLearning, isTranslated, onToggleTranslation }) => {
  return (
    <div className="absolute bottom-10 left-1/2 -translate-x-1/2 bg-white/95 backdrop-blur-md shadow-2xl border border-slate-200/60 px-2 py-2 rounded-2xl flex items-center gap-2 z-20">
      <button 
        onClick={onDynamicExplain}
        className="px-4 py-2 rounded-xl flex items-center gap-2 transition-all bg-pixiu text-white hover:bg-pixiu-dark shadow-md shadow-pixiu/20 active:scale-95"
        title="动态解释模式"
      >
        <Zap size={16} />
        <span className="text-sm font-semibold">动态解释</span>
      </button>

      <button 
        onClick={onToggleTranslation}
        className={`px-4 py-2 rounded-xl flex items-center gap-2 transition-all border font-semibold text-sm active:scale-95 ${
          isTranslated 
          ? 'bg-amber-50 text-amber-600 border-amber-200 shadow-sm' 
          : 'bg-white text-slate-600 border-slate-200 hover:border-pixiu hover:text-pixiu'
        }`}
      >
        <Languages size={16} className={isTranslated ? 'text-amber-500' : 'text-pixiu'}/>
        <span>全景翻译</span>
      </button>

      <div className="w-[1px] h-6 bg-slate-200 mx-1"></div>

      <button 
        onClick={onCriticalReading}
        className="px-4 py-2 rounded-xl flex items-center gap-2 transition-all border border-slate-200 bg-white text-slate-600 font-semibold text-sm hover:border-pixiu hover:text-pixiu hover:bg-pixiu/5 active:scale-95"
        title="批判性阅读"
      >
        <ShieldAlert size={16} className="text-pixiu" />
        <span>批判阅读</span>
      </button>

      <button
        onClick={onSocraticLearning}
        className="px-4 py-2 rounded-xl flex items-center gap-2 transition-all border border-slate-200 bg-white text-slate-600 font-semibold text-sm hover:border-pixiu hover:text-pixiu hover:bg-pixiu/5 active:scale-95"
      >
        <Sparkles size={16} className="text-pixiu" />
        <span>引导式学习</span>
      </button>
    </div>
  );
};

export default PdfToolbar;
