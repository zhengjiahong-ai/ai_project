import { useState, useEffect, useCallback } from 'react';
import { BookOpen, Plus, Trash2, Save, ChevronRight, FileText, Hash, Download } from 'lucide-react';
import { loadNotes, upsertNote, deleteNote } from '../services/notesStore';
import { loadHighlights, getBookmarks } from '../services/highlightStore';

/**
 * ReadingNotesPanel – Per-paper reading notes organized by section.
 *
 * Props:
 *   pdfId: string
 *   paperSkeleton: { sections?: Array<{ id, title, pageIndex }> }
 *   currentPageIndex: number
 *   onJumpToPage: (pageIndex: number) => void
 *   theme?: 'light' | 'dark'
 */
export default function ReadingNotesPanel({
  pdfId,
  paperSkeleton,
  currentPageIndex,
  onJumpToPage,
  theme = 'light',
}) {
  const [notes, setNotes] = useState([]);
  const [activeSectionId, setActiveSectionId] = useState(null);
  const [editingNote, setEditingNote] = useState(null); // { id?, sectionId, content }
  const [isLoading, setIsLoading] = useState(true);
  const [subTab, setSubTab] = useState('notes'); // 'notes' | 'bookmarks'
  const [showExportMenu, setShowExportMenu] = useState(false);

  const isDark = theme === 'dark';
  const sections = paperSkeleton?.sections || [];

  // Load notes on mount / pdfId change
  useEffect(() => {
    if (!pdfId) return;
    setIsLoading(true);
    loadNotes(pdfId)
      .then((data) => setNotes(data || []))
      .finally(() => setIsLoading(false));
    setActiveSectionId(null);
    setEditingNote(null);
  }, [pdfId]);

  // Start editing a new or existing note
  const startEdit = useCallback((sectionId, existingNote) => {
    setActiveSectionId(sectionId);
    setEditingNote(
      existingNote
        ? { ...existingNote }
        : { sectionId, content: '', pageIndex: currentPageIndex }
    );
  }, [currentPageIndex]);

  // Save note
  const handleSave = useCallback(async () => {
    if (!editingNote || !editingNote.content.trim()) return;
    const updated = await upsertNote(pdfId, {
      ...editingNote,
      pdfId,
    });
    setNotes(updated);
    setEditingNote(null);
  }, [editingNote, pdfId]);

  // Delete note
  const handleDelete = useCallback(async (noteId) => {
    const updated = await deleteNote(pdfId, noteId);
    setNotes(updated);
    if (editingNote?.id === noteId) setEditingNote(null);
  }, [pdfId, editingNote]);

  // Insert page reference into editor
  const insertPageRef = useCallback(() => {
    if (!editingNote) return;
    setEditingNote({
      ...editingNote,
      content: editingNote.content + ` [p.${currentPageIndex + 1}]`,
    });
  }, [editingNote, currentPageIndex]);

  // Export notes as Markdown or JSON
  const handleExport = useCallback(async (format) => {
    const highlights = await loadHighlights(pdfId);
    const bookmarks = await getBookmarks(pdfId);
    const title = paperSkeleton?.title || pdfId || 'Untitled';

    let content, mimeType, filename;

    if (format === 'markdown') {
      content = [
        `# ${title}`,
        '',
        '## Highlights',
        ...(highlights.length > 0
          ? highlights.map((h) => {
              const page = (h.pageIndex ?? h.position?.pageIndex ?? 0) + 1;
              const color = h.color || 'yellow';
              return `- [p.${page}] ${h.text || '(no text)'} (${color})`;
            })
          : ['- No highlights']),
        '',
        '## Notes',
        ...notes.map((n) => {
          const sectionLabel = sections.find(
            (s) => (s.id || s.title) === n.sectionId
          )?.title || 'General';
          return `### ${sectionLabel}\n${n.content}${n.pageIndex != null ? `\n\n[p.${n.pageIndex + 1}]` : ''}\n`;
        }),
        bookmarks.length > 0 ? '\n## Bookmarks' : '',
        ...bookmarks.map((b) => `- [p.${b.pageIndex + 1}] ${b.label || ''}`),
      ].join('\n');
      mimeType = 'text/markdown';
      filename = `${title.replace(/[^a-zA-Z0-9一-鿿]/g, '_')}_notes.md`;
    } else {
      // JSON
      content = JSON.stringify({
        title,
        pdfId,
        exportedAt: new Date().toISOString(),
        highlights,
        notes,
        bookmarks,
      }, null, 2);
      mimeType = 'application/json';
      filename = `${title.replace(/[^a-zA-Z0-9一-鿿]/g, '_')}_notes.json`;
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [pdfId, notes, paperSkeleton, sections]);

  // Group notes by section
  const notesBySection = {};
  sections.forEach((s) => { notesBySection[s.id || s.title] = []; });
  notes.forEach((n) => {
    const key = n.sectionId || '__unsorted__';
    if (!notesBySection[key]) notesBySection[key] = [];
    notesBySection[key].push(n);
  });

  if (isLoading) {
    return <div className="p-4 text-center text-sm text-gray-400">Loading notes...</div>;
  }

  return (
    <div className={`flex h-full flex-col ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
      {/* Sub-tab bar */}
      <div className="flex items-center border-b dark:border-gray-700">
        <button
          onClick={() => setSubTab('notes')}
          className={`flex-1 px-3 py-2 text-xs font-medium ${
            subTab === 'notes'
              ? 'border-b-2 border-blue-500 text-blue-600'
              : 'text-gray-400'
          }`}
        >
          Notes
        </button>
        <button
          onClick={() => setSubTab('bookmarks')}
          className={`flex-1 px-3 py-2 text-xs font-medium ${
            subTab === 'bookmarks'
              ? 'border-b-2 border-blue-500 text-blue-600'
              : 'text-gray-400'
          }`}
        >
          Bookmarks
        </button>
      </div>

      {/* Section + Notes List */}
      {subTab === 'notes' && (
        <div className="flex-1 overflow-y-auto">
          {/* New Note button */}
          <div className="flex items-center justify-between border-b p-3 dark:border-gray-700">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <BookOpen size={16} />
              Reading Notes
            </h3>
            <div className="flex items-center gap-2">
              {/* Export dropdown */}
              <div className="relative">
                <button
                  onClick={() => setShowExportMenu(!showExportMenu)}
                  className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
                  title="Export"
                >
                  <Download size={14} /> Export
                </button>
                {showExportMenu && (
                  <div className={`absolute right-0 top-full z-20 mt-1 rounded border shadow-lg ${isDark ? 'border-gray-600 bg-gray-700' : 'border-gray-200 bg-white'}`}>
                    <button onClick={() => { handleExport('markdown'); setShowExportMenu(false); }}
                      className="block w-full px-4 py-2 text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-600">
                      Export as Markdown
                    </button>
                    <button onClick={() => { handleExport('json'); setShowExportMenu(false); }}
                      className="block w-full px-4 py-2 text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-600">
                      Export as JSON
                    </button>
                  </div>
                )}
              </div>
              <button
                onClick={() => startEdit('__unsorted__', null)}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 dark:text-blue-400"
              >
                <Plus size={14} /> New Note
              </button>
            </div>
          </div>

          {sections.length === 0 && (
            <p className="p-4 text-center text-xs text-gray-400">
              No sections available. Upload a paper to see its outline.
            </p>
          )}

          {sections.map((section) => {
            const sectionNotes = notesBySection[section.id || section.title] || [];
            const isActive = activeSectionId === (section.id || section.title);

            return (
              <div key={section.id || section.title} className="border-b dark:border-gray-700">
                {/* Section Header */}
                <button
                  onClick={() => setActiveSectionId(isActive ? null : (section.id || section.title))}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium hover:bg-gray-50 dark:hover:bg-gray-800 ${
                    isActive ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                  }`}
                >
                  {isActive ? <ChevronRight size={12} className="rotate-90" /> : <ChevronRight size={12} />}
                  <span className="truncate">{section.title || `Section ${section.pageIndex + 1}`}</span>
                  <span className="ml-auto text-gray-400">{sectionNotes.length}</span>
                </button>

                {/* Section Notes + Editor */}
                {isActive && (
                  <div className="px-3 pb-3">
                    {sectionNotes.map((note) => (
                      <div key={note.id} className="mb-2 rounded border p-2 text-xs dark:border-gray-700">
                        {editingNote?.id === note.id ? (
                          /* Edit existing */
                          <div className="space-y-2">
                            <textarea
                              value={editingNote.content}
                              onChange={(e) => setEditingNote({ ...editingNote, content: e.target.value })}
                              className={`w-full rounded border p-2 text-xs ${isDark ? 'bg-gray-700 border-gray-600 text-gray-100' : 'border-gray-300 bg-white'}`}
                              rows={4}
                              placeholder="Write your note..."
                            />
                            <div className="flex items-center gap-2">
                              <button onClick={handleSave} className="flex items-center gap-1 rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700">
                                <Save size={12} /> Save
                              </button>
                              <button onClick={insertPageRef} className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700">
                                <Hash size={12} /> p.{currentPageIndex + 1}
                              </button>
                              <button onClick={() => setEditingNote(null)} className="ml-auto text-xs text-gray-400">Cancel</button>
                            </div>
                          </div>
                        ) : (
                          /* Display note */
                          <div>
                            <p className="whitespace-pre-wrap leading-relaxed">{note.content}</p>
                            <div className="mt-1 flex items-center gap-2 text-gray-400">
                              {note.pageIndex != null && (
                                <button
                                  onClick={() => onJumpToPage?.(note.pageIndex)}
                                  className="text-blue-500 hover:underline"
                                >
                                  [p.{note.pageIndex + 1}]
                                </button>
                              )}
                              <span className="text-[10px]">
                                {note.updatedAt ? new Date(note.updatedAt).toLocaleDateString() : ''}
                              </span>
                              <button onClick={() => startEdit(section.id || section.title, note)} className="ml-auto text-gray-400 hover:text-blue-500">Edit</button>
                              <button onClick={() => handleDelete(note.id)} className="text-gray-400 hover:text-red-500">
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}

                    {/* New note button for this section */}
                    {(!editingNote || editingNote.sectionId !== (section.id || section.title)) && (
                      <button
                        onClick={() => startEdit(section.id || section.title, null)}
                        className="flex w-full items-center gap-1 rounded border border-dashed p-2 text-xs text-gray-400 hover:border-blue-400 hover:text-blue-500 dark:border-gray-600"
                      >
                        <Plus size={12} /> Add note to this section
                      </button>
                    )}

                    {/* New note editor */}
                    {editingNote && !editingNote.id && editingNote.sectionId === (section.id || section.title) && (
                      <div className="mt-2 space-y-2">
                        <textarea
                          value={editingNote.content}
                          onChange={(e) => setEditingNote({ ...editingNote, content: e.target.value })}
                          className={`w-full rounded border p-2 text-xs ${isDark ? 'bg-gray-700 border-gray-600 text-gray-100' : 'border-gray-300 bg-white'}`}
                          rows={3}
                          placeholder="Write your note for this section..."
                        />
                        <div className="flex items-center gap-2">
                          <button onClick={handleSave} className="flex items-center gap-1 rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700">
                            <Save size={12} /> Save
                          </button>
                          <button onClick={insertPageRef} className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700">
                            <Hash size={12} /> p.{currentPageIndex + 1}
                          </button>
                          <button onClick={() => setEditingNote(null)} className="ml-auto text-xs text-gray-400">Cancel</button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {subTab === 'bookmarks' && (
        <BookmarkList pdfId={pdfId} onJumpToPage={onJumpToPage} theme={theme} />
      )}
    </div>
  );
}

/**
 * BookmarkList – renders saved bookmarks for a PDF, each clickable to jump to page.
 */
function BookmarkList({ pdfId, onJumpToPage, theme }) {
  const [bookmarks, setBookmarks] = useState([]);
  const isDark = theme === 'dark';

  useEffect(() => {
    if (!pdfId) return;
    import('../services/highlightStore').then(({ getBookmarks }) => {
      getBookmarks(pdfId).then(setBookmarks);
    });
  }, [pdfId]);

  if (bookmarks.length === 0) {
    return (
      <p className="p-4 text-center text-xs text-gray-400">
        No bookmarks yet. Click ☆ in the PDF toolbar to add.
      </p>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-2">
      {bookmarks.map((b) => (
        <button
          key={b.pageIndex}
          onClick={() => onJumpToPage?.(b.pageIndex)}
          className={`flex w-full items-center gap-2 rounded p-2 text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-800 ${
            isDark ? 'text-gray-300' : 'text-gray-700'
          }`}
        >
          <span>⭐</span>
          <span>{b.label || `Page ${b.pageIndex + 1}`}</span>
          <span className="ml-auto text-[10px] text-gray-400">
            {b.createdAt ? new Date(b.createdAt).toLocaleDateString() : ''}
          </span>
        </button>
      ))}
    </div>
  );
}
