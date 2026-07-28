import React, { useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { Bold, Italic, Heading, List, Code, Hash, Eye, Edit3 } from 'lucide-react';

const MarkdownNoteEditor = ({
  value,
  onChange,
  onSave,
  onCancel,
  onInsertPageRef,
  currentPage,
  isDark = false,
  placeholder = 'Write your note...',
  rows = 4,
}) => {
  const [previewMode, setPreviewMode] = useState(false);

  const insertFormatting = useCallback((prefix, suffix = '') => {
    const textarea = document.activeElement;
    if (textarea?.tagName !== 'TEXTAREA') return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = value.substring(start, end);
    const newText = value.substring(0, start) + prefix + selected + suffix + value.substring(end);
    onChange(newText);
    // Restore focus and selection
    setTimeout(() => {
      textarea.focus();
      const newCursor = start + prefix.length + selected.length + suffix.length;
      textarea.setSelectionRange(newCursor, newCursor);
    }, 0);
  }, [value, onChange]);

  const pageRef = currentPage != null ? `[p.${currentPage + 1}]` : '[p.N]';

  const toolbarButton = (icon, label, prefix, suffix = '') => (
    <button
      type="button"
      onClick={() => insertFormatting(prefix, suffix)}
      title={label}
      className={`rounded p-1.5 text-xs transition ${
        isDark ? 'hover:bg-gray-600 text-gray-300' : 'hover:bg-gray-200 text-gray-600'
      }`}
    >
      {icon}
    </button>
  );

  const inputClasses = `w-full rounded border p-2 text-xs font-mono resize-y ${
    isDark ? 'bg-gray-700 border-gray-600 text-gray-100' : 'border-gray-300 bg-white text-gray-900'
  }`;

  const previewClasses = `prose prose-sm max-w-none rounded border p-2 text-xs min-h-[60px] ${
    isDark ? 'bg-gray-750 border-gray-600 text-gray-100 prose-invert' : 'border-gray-300 bg-gray-50 text-gray-900'
  }`;

  // Custom renderer for [p.N] page references
  const markdownComponents = {
    a: ({ href, children, ...props }) => {
      const pageMatch = href?.match(/^page:(\d+)$/);
      if (pageMatch) {
        const pageNum = parseInt(pageMatch[1], 10);
        return (
          <button
            type="button"
            onClick={(e) => { e.preventDefault(); onInsertPageRef?.(pageNum - 1); }}
            className="inline-flex items-center gap-0.5 rounded bg-blue-100 px-1 py-0 text-blue-700 hover:bg-blue-200 dark:bg-blue-900 dark:text-blue-300 dark:hover:bg-blue-800"
            {...props}
          >
            {children}
          </button>
        );
      }
      return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
    },
  };

  return (
    <div className="space-y-2">
      {/* Toolbar */}
      <div className={`flex items-center gap-1 rounded-lg border p-1 ${isDark ? 'border-gray-600 bg-gray-800' : 'border-gray-200 bg-gray-50'}`}>
        {toolbarButton(<Bold size={14} />, 'Bold', '**', '**')}
        {toolbarButton(<Italic size={14} />, 'Italic', '*', '*')}
        {toolbarButton(<Heading size={14} />, 'Heading', '### ')}
        {toolbarButton(<List size={14} />, 'Unordered List', '- ')}
        {toolbarButton(<Code size={14} />, 'Code', '`', '`')}
        <span className="mx-0.5 h-4 w-px bg-gray-300 dark:bg-gray-600" />
        <button
          type="button"
          onClick={onInsertPageRef || (() => insertFormatting(pageRef))}
          title={`Insert page reference: ${pageRef}`}
          className={`rounded p-1.5 text-xs transition ${
            isDark ? 'hover:bg-gray-600 text-gray-300' : 'hover:bg-gray-200 text-gray-600'
          }`}
        >
          <Hash size={14} />
        </button>
        <span className="ml-auto" />
        <button
          type="button"
          onClick={() => setPreviewMode(!previewMode)}
          title={previewMode ? 'Edit' : 'Preview'}
          className={`rounded p-1.5 text-xs transition ${
            isDark ? 'hover:bg-gray-600 text-gray-300' : 'hover:bg-gray-200 text-gray-600'
          }`}
        >
          {previewMode ? <Edit3 size={14} /> : <Eye size={14} />}
        </button>
      </div>

      {/* Editor / Preview */}
      {previewMode ? (
        <div className={previewClasses}>
          {value?.trim() ? (
            <ReactMarkdown components={markdownComponents}>
              {value || '*Nothing to preview*'}
            </ReactMarkdown>
          ) : (
            <span className="text-gray-400 italic">Nothing to preview</span>
          )}
        </div>
      ) : (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={inputClasses}
          rows={rows}
          placeholder={placeholder}
        />
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        {onSave && (
          <button onClick={onSave} className="flex items-center gap-1 rounded bg-blue-600 px-2.5 py-1 text-xs text-white hover:bg-blue-700">
            Save
          </button>
        )}
        {onCancel && (
          <button onClick={onCancel} className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            Cancel
          </button>
        )}
        {onInsertPageRef && currentPage != null && (
          <button onClick={onInsertPageRef} className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700">
            <Hash size={12} /> p.{currentPage + 1}
          </button>
        )}
      </div>
    </div>
  );
};

export default MarkdownNoteEditor;
