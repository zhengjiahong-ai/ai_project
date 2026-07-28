import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import ReadingNotesPanel from './ReadingNotesPanel.jsx';

// Mock the service modules
vi.mock('../services/notesStore', () => ({
  loadNotes: vi.fn(),
  upsertNote: vi.fn(),
  deleteNote: vi.fn(),
}));

vi.mock('../services/highlightStore', () => ({
  loadHighlights: vi.fn(),
  getBookmarks: vi.fn(),
}));

import { loadNotes, upsertNote, deleteNote } from '../services/notesStore';
import { loadHighlights, getBookmarks } from '../services/highlightStore';

describe('ReadingNotesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadNotes.mockResolvedValue([]);
    loadHighlights.mockResolvedValue([]);
    getBookmarks.mockResolvedValue([]);
  });

  it('renders loading state when pdfId is null', () => {
    render(
      <ReadingNotesPanel
        pdfId={null}
        paperSkeleton={{}}
        currentPageIndex={0}
        onJumpToPage={() => {}}
      />,
    );
    expect(screen.getByText('Loading notes...')).toBeInTheDocument();
  });

  it('renders empty sections message when paperSkeleton has no sections', async () => {
    render(
      <ReadingNotesPanel
        pdfId="pdf-1"
        paperSkeleton={{ sections: [] }}
        currentPageIndex={0}
        onJumpToPage={() => {}}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByText('No sections available. Upload a paper to see its outline.'),
      ).toBeInTheDocument();
    });
  });

  it('renders section list from paperSkeleton', async () => {
    const sections = [
      { id: 's1', title: 'Introduction', pageIndex: 0 },
      { id: 's2', title: 'Methods', pageIndex: 1 },
      { id: 's3', title: 'Results', pageIndex: 2 },
    ];

    render(
      <ReadingNotesPanel
        pdfId="pdf-1"
        paperSkeleton={{ sections }}
        currentPageIndex={0}
        onJumpToPage={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Introduction')).toBeInTheDocument();
      expect(screen.getByText('Methods')).toBeInTheDocument();
      expect(screen.getByText('Results')).toBeInTheDocument();
    });
  });

  it('expands and collapses a section on click', async () => {
    const sections = [{ id: 's1', title: 'Introduction', pageIndex: 0 }];

    render(
      <ReadingNotesPanel
        pdfId="pdf-1"
        paperSkeleton={{ sections }}
        currentPageIndex={0}
        onJumpToPage={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Introduction')).toBeInTheDocument();
    });

    // Click to expand
    fireEvent.click(screen.getByText('Introduction'));
    await waitFor(() => {
      expect(screen.getByText('Add note to this section')).toBeInTheDocument();
    });

    // Click again to collapse
    fireEvent.click(screen.getByText('Introduction'));
    await waitFor(() => {
      expect(screen.queryByText('Add note to this section')).not.toBeInTheDocument();
    });
  });

  it('shows note editor when clicking add note button', async () => {
    const sections = [{ id: 's1', title: 'Introduction', pageIndex: 0 }];

    render(
      <ReadingNotesPanel
        pdfId="pdf-1"
        paperSkeleton={{ sections }}
        currentPageIndex={0}
        onJumpToPage={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Introduction')).toBeInTheDocument();
    });

    // Expand the section first
    fireEvent.click(screen.getByText('Introduction'));
    await waitFor(() => {
      expect(screen.getByText('Add note to this section')).toBeInTheDocument();
    });

    // Click add note button
    fireEvent.click(screen.getByText('Add note to this section'));
    await waitFor(() => {
      expect(
        screen.getByPlaceholderText('Write your note for this section...'),
      ).toBeInTheDocument();
    });
  });

  it('renders Export and New Note buttons', async () => {
    loadNotes.mockResolvedValue([]);

    render(
      <ReadingNotesPanel
        pdfId="pdf-1"
        paperSkeleton={{ sections: [{ id: 's1', title: 'Introduction' }] }}
        currentPageIndex={0}
        onJumpToPage={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Export')).toBeInTheDocument();
      expect(screen.getByText('New Note')).toBeInTheDocument();
    });
  });

  it('switches between Notes and Bookmarks subtabs', async () => {
    render(
      <ReadingNotesPanel
        pdfId="pdf-1"
        paperSkeleton={{ sections: [{ id: 's1', title: 'Introduction' }] }}
        currentPageIndex={0}
        onJumpToPage={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Notes')).toBeInTheDocument();
      expect(screen.getByText('Bookmarks')).toBeInTheDocument();
    });

    // Click Bookmarks tab
    fireEvent.click(screen.getByText('Bookmarks'));
    await waitFor(() => {
      expect(
        screen.getByText('No bookmarks yet. Click ☆ in the PDF toolbar to add.'),
      ).toBeInTheDocument();
    });
  });

  it('has a working save button after editing a note', async () => {
    upsertNote.mockResolvedValue([{ id: 'n1', sectionId: 's1', content: 'My note' }]);
    const sections = [{ id: 's1', title: 'Introduction', pageIndex: 0 }];

    render(
      <ReadingNotesPanel
        pdfId="pdf-1"
        paperSkeleton={{ sections }}
        currentPageIndex={0}
        onJumpToPage={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Introduction')).toBeInTheDocument();
    });

    // Expand section
    fireEvent.click(screen.getByText('Introduction'));
    await waitFor(() => {
      expect(screen.getByText('Add note to this section')).toBeInTheDocument();
    });

    // Open new note editor
    fireEvent.click(screen.getByText('Add note to this section'));
    await waitFor(() => {
      expect(
        screen.getByPlaceholderText('Write your note for this section...'),
      ).toBeInTheDocument();
    });

    // Type content and save
    const textarea = screen.getByPlaceholderText('Write your note for this section...');
    fireEvent.change(textarea, { target: { value: 'My test note' } });
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(upsertNote).toHaveBeenCalled();
    });
  });
});
