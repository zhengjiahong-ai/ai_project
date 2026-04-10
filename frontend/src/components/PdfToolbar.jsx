import { Languages, ShieldAlert, Sparkles, Zap } from 'lucide-react';

const PdfToolbar = ({
  onDynamicExplain,
  onCriticalReading,
  onSocraticLearning,
  isTranslated,
  onToggleTranslation,
}) => {
  return (
    <div className="theme-toolbar absolute bottom-10 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-2xl px-2 py-2 backdrop-blur-md">
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
        className={`theme-toolbar-button flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-all active:scale-95 ${
          isTranslated ? 'theme-toolbar-button-active' : ''
        }`}
      >
        <Languages size={16} className={isTranslated ? 'text-amber-400' : 'text-pixiu'} />
        <span>全景翻译</span>
      </button>

      <div className="theme-divider mx-1 h-6 w-[1px]" />

      <button
        onClick={onCriticalReading}
        className="theme-toolbar-button flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-all active:scale-95"
        title="批判性阅读"
      >
        <ShieldAlert size={16} className="text-pixiu" />
        <span>批判阅读</span>
      </button>

      <button
        onClick={onSocraticLearning}
        className="theme-toolbar-button flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-all active:scale-95"
        title="引导式学习"
      >
        <Sparkles size={16} className="text-pixiu" />
        <span>引导式学习</span>
      </button>
    </div>
  );
};

export default PdfToolbar;
