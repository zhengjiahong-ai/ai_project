import { Languages, ShieldAlert, Sparkles, Zap } from 'lucide-react';

const PdfToolbar = ({
  onDynamicExplain,
  onCriticalReading,
  onSocraticLearning,
  isTranslated,
  onToggleTranslation,
}) => {
  return (
    <div className="absolute bottom-10 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-2xl border border-slate-200/60 bg-white/95 px-2 py-2 shadow-2xl backdrop-blur-md">
      <button
        onClick={onDynamicExplain}
        className="flex items-center gap-2 rounded-xl bg-pixiu px-4 py-2 text-white shadow-md shadow-pixiu/20 transition-all hover:bg-pixiu-dark active:scale-95"
        title="动态解释模式"
      >
        <Zap size={16} />
        <span className="text-sm font-semibold">动态解释</span>
      </button>

      <button
        onClick={onToggleTranslation}
        className={`flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-semibold transition-all active:scale-95 ${
          isTranslated
            ? 'border-amber-200 bg-amber-50 text-amber-600 shadow-sm'
            : 'border-slate-200 bg-white text-slate-600 hover:border-pixiu hover:text-pixiu'
        }`}
      >
        <Languages size={16} className={isTranslated ? 'text-amber-500' : 'text-pixiu'} />
        <span>全景翻译</span>
      </button>

      <div className="mx-1 h-6 w-[1px] bg-slate-200" />

      <button
        onClick={onCriticalReading}
        className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 transition-all hover:border-pixiu hover:bg-pixiu/5 hover:text-pixiu active:scale-95"
        title="批判性阅读"
      >
        <ShieldAlert size={16} className="text-pixiu" />
        <span>批判阅读</span>
      </button>

      <button
        onClick={onSocraticLearning}
        className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 transition-all hover:border-pixiu hover:bg-pixiu/5 hover:text-pixiu active:scale-95"
        title="引导式学习"
      >
        <Sparkles size={16} className="text-pixiu" />
        <span>引导式学习</span>
      </button>
    </div>
  );
};

export default PdfToolbar;
