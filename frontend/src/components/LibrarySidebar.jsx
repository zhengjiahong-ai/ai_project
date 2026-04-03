import React from 'react';
import { X, FileText, Trash2, Clock } from 'lucide-react';

const LibrarySidebar = ({ isOpen, onClose, papers, currentPdfId, onSelectPaper, onDeletePaper }) => {
  if (!isOpen) return null;

  return (
    <>
      <div 
        className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-40 transition-opacity"
        onClick={onClose}
      />
      <div className="fixed top-0 left-0 bottom-0 w-80 bg-white shadow-2xl z-50 flex flex-col transform transition-transform duration-300">
        <div className="p-4 border-b flex items-center justify-between bg-slate-50">
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <BookOpenIcon />
            我的论文库
          </h2>
          <button 
            onClick={onClose}
            className="p-1 rounded-md text-slate-400 hover:bg-slate-200 hover:text-slate-600 transition"
          >
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/50">
          {papers.length === 0 ? (
            <div className="text-center text-sm text-slate-500 mt-10">
              空空如也，赶快上传第一篇论文吧！
            </div>
          ) : (
            papers.map(paper => (
              <div 
                key={paper.id}
                onClick={() => {
                  onSelectPaper(paper.id);
                  onClose();
                }}
                className={`group cursor-pointer p-4 rounded-xl border transition-all ${
                  currentPdfId === paper.id
                    ? 'border-pixiu/40 bg-pixiu/5 shadow-sm'
                    : 'border-slate-200 bg-white hover:border-pixiu/30 hover:shadow-sm'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2 overflow-hidden flex-1">
                    <FileText size={16} className={`shrink-0 mt-0.5 ${currentPdfId === paper.id ? 'text-pixiu' : 'text-slate-400'}`} />
                    <span className="text-sm font-semibold text-slate-700 leading-snug line-clamp-2">
                      {paper.filename}
                    </span>
                  </div>
                </div>
                
                <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                  <span className="flex items-center gap-1">
                    <Clock size={12} />
                    {new Date(paper.timestamp).toLocaleDateString()}
                  </span>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeletePaper(paper.id);
                    }}
                    className="p-1.5 rounded bg-slate-100 opacity-0 group-hover:opacity-100 hover:bg-red-100 hover:text-red-600 transition-all text-slate-400"
                    title="删除"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
};

const BookOpenIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-pixiu">
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path>
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path>
  </svg>
);

export default LibrarySidebar;
