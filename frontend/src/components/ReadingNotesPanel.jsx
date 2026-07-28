import { useState, useEffect, useCallback } from 'react';
import { BookOpen, Plus, Trash2, Save, ChevronRight, FileText, Hash } from 'lucide-react';
import { loadNotes, upsertNote, deleteNote } from '../services/notesStore';

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
      {/* Header */}
      <div className="flex items-center justify-between border-b p-3 dark:border-gray-700">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <BookOpen size={16} />
          Reading Notes
        </h3>
        <button
          onClick={() => startEdit('__unsorted__', null)}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 dark:text-blue-400"
        >
          <Plus size={14} /> New Note
        </button>
      </div>

      {/* Section + Notes List */}
      <div className="flex-1 overflow-y-auto">
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
    </div>
  );
}
