import React from 'react';
import { Clock, FileText, Trash2, X } from 'lucide-react';

const LibrarySidebar = ({ isOpen, onClose, papers, currentPdfId, onSelectPaper, onDeletePaper }) => {
  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-slate-950/35 backdrop-blur-sm transition-opacity" onClick={onClose} />
      <div className="theme-panel fixed bottom-0 left-0 top-0 z-50 flex w-80 flex-col shadow-2xl">
        <div className="theme-panel-muted theme-border flex items-center justify-between border-b p-4">
          <h2 className="theme-text-primary flex items-center gap-2 text-lg font-bold">
            <BookOpenIcon />
            我的论文库
          </h2>
          <button onClick={onClose} className="theme-icon-button rounded-md p-1 transition">
            <X size={20} />
          </button>
        </div>

        <div className="theme-panel-muted flex-1 space-y-3 overflow-y-auto p-4">
          {papers.length === 0 ? (
            <div className="theme-text-secondary mt-10 text-center text-sm">空空如也，快上传第一篇论文吧。</div>
          ) : (
            papers.map((paper) => {
              const isActive = currentPdfId === paper.id;

              return (
                <div
                  key={paper.id}
                  onClick={() => {
                    onSelectPaper(paper.id);
                    onClose();
                  }}
                  className={`group cursor-pointer rounded-xl p-4 transition-all ${
                    isActive ? 'theme-markdown-panel theme-border border shadow-sm' : 'theme-card'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex flex-1 items-start gap-2 overflow-hidden">
                      <FileText size={16} className={`mt-0.5 shrink-0 ${isActive ? 'text-pixiu' : 'theme-text-muted'}`} />
                      <span className="theme-text-primary line-clamp-2 text-sm font-semibold leading-snug">
                        {paper.filename}
                      </span>
                    </div>
                  </div>

                  <div className="theme-text-muted mt-3 flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1">
                      <Clock size={12} />
                      {new Date(paper.timestamp).toLocaleDateString()}
                    </span>
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        onDeletePaper(paper.id);
                      }}
                      className="theme-danger-button rounded p-1.5 opacity-0 transition-all group-hover:opacity-100"
                      title="删除"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </>
  );
};

const BookOpenIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="text-pixiu"
  >
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
  </svg>
);

export default LibrarySidebar;
