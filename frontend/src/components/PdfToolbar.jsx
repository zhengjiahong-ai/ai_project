import { Languages, Zap } from 'lucide-react';

const PdfToolbar = ({
  onDynamicExplain,
  isTranslated,
  onToggleTranslation,
}) => {
  return (
    <div className="theme-toolbar absolute bottom-10 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-2xl px-2 py-2 backdrop-blur-md">
      <button
        type="button"
        onClick={onDynamicExplain}
        className="flex items-center gap-2 rounded-xl bg-pixiu px-4 py-2 text-white shadow-md shadow-pixiu/20 transition-all hover:bg-pixiu-dark active:scale-95"
        title="动态解释模式"
      >
        <Zap size={16} />
        <span className="text-sm font-semibold">动态解释</span>
      </button>

      <button
        type="button"
        onClick={onToggleTranslation}
        className={`theme-toolbar-button flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-all active:scale-95 ${
          isTranslated ? 'theme-toolbar-button-active' : ''
        }`}
        title="切换全景翻译"
      >
        <Languages size={16} className={isTranslated ? 'text-amber-400' : 'text-pixiu'} />
        <span>全景翻译</span>
      </button>
    </div>
  );
};

export default PdfToolbar;
