import React from 'react';
import { Worker, Viewer } from '@react-pdf-viewer/core';
import { defaultLayoutPlugin } from '@react-pdf-viewer/default-layout';
import { highlightPlugin } from '@react-pdf-viewer/highlight';
import { Sparkles } from 'lucide-react'; // 补全图标引用
import '@react-pdf-viewer/highlight/lib/styles/index.css';
// 引入样式（必须！）
import '@react-pdf-viewer/core/lib/styles/index.css';
import '@react-pdf-viewer/default-layout/lib/styles/index.css';

/**
 * PDF 查看器组件
 * @param {string} fileUrl - PDF 文件的 URL（可以是本地 blob URL 或远程 URL）
 */
const PdfViewer = ({ fileUrl, onSelection }) => {
  const defaultLayoutPluginInstance = defaultLayoutPlugin();

  // 使用 CDN 加载 worker，这是最稳妥的办法
  // 也可以使用本地 worker，但需要配置 vite 的静态资源处理
  const workerUrl = `https://unpkg.com/pdfjs-dist@${import.meta.env.VITE_PDFJS_VERSION || '3.4.120'}/build/pdf.worker.min.js`;
  const highlightPluginInstance = highlightPlugin({
    renderHighlightTarget: (props) => (
      <div
        className="absolute z-50 bg-white shadow-2xl border border-blue-100 p-1 rounded-lg flex items-center"
        style={{
          top: `${props.selectionRegion.top + props.selectionRegion.height}%`,
          left: `${props.selectionRegion.left}%`,
          transform: 'translateY(10px)',
        }}
      >
        <button
          onClick={() => {
            onSelection(props.selectedText); // 修复：调用父组件传入的方法
            props.cancel(); // 选完后自动取消高亮条
          }}
          className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white text-xs font-bold rounded-md hover:bg-blue-700 transition"
        >
          <Sparkles size={12} /> AI 解释
        </button>
      </div>
    ),
  });
  return (
    <div className="h-full w-full">
      {fileUrl ? (
        <Worker workerUrl={workerUrl}>
          <Viewer 
            fileUrl={fileUrl} 
            plugins={[defaultLayoutPluginInstance, highlightPluginInstance]} 
            theme="light"
          />
        </Worker>
      ) : (
        <div className="flex flex-col items-center justify-center h-full text-slate-400 bg-slate-50">
          <svg 
            className="w-16 h-16 mb-4 text-slate-300" 
            fill="none" 
            stroke="currentColor" 
            viewBox="0 0 24 24"
          >
            <path 
              strokeLinecap="round" 
              strokeLinejoin="round" 
              strokeWidth={2} 
              d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" 
            />
          </svg>
          <p className="text-lg font-medium mb-2">暂无预览内容</p>
          <p className="text-sm">请从右上角上传一份 PDF 论文</p>
        </div>
      )}
    </div>
  );
};

export default PdfViewer;
