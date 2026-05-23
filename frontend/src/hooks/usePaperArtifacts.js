import { useCallback, useState } from 'react';
import {
  createInsightArtifact,
  normalizeInsightArtifacts,
  updateInsightArtifact,
} from '../components/artifactModel.js';

export const usePaperArtifacts = () => {
  const [notes, setNotes] = useState([]);
  const [pdfHighlights, setPdfHighlights] = useState([]);
  const [workbenchCards, setWorkbenchCards] = useState([]);

  const addNote = useCallback((noteData) => {
    setNotes((previousNotes) => [
      {
        id: Date.now(),
        ...noteData,
        time: new Date().toLocaleTimeString(),
      },
      ...previousNotes,
    ]);
  }, []);

  const resetArtifacts = useCallback(() => {
    setNotes([]);
    setPdfHighlights([]);
    setWorkbenchCards([]);
  }, []);

  const replaceWorkbenchCards = useCallback((nextCards) => {
    setWorkbenchCards(normalizeInsightArtifacts(nextCards));
  }, []);

  const captureArtifact = useCallback((artifactInput) => {
    const nextArtifact = createInsightArtifact(artifactInput);
    setWorkbenchCards((previousCards) => normalizeInsightArtifacts([nextArtifact, ...previousCards]));
    return nextArtifact;
  }, []);

  const removeArtifact = useCallback((artifactId) => {
    setWorkbenchCards((previousCards) => previousCards.filter((artifact) => artifact.artifactId !== artifactId));
  }, []);

  const toggleArtifactPinned = useCallback((artifactId) => {
    setWorkbenchCards((previousCards) =>
      normalizeInsightArtifacts(
        previousCards.map((artifact) =>
          artifact.artifactId === artifactId
            ? updateInsightArtifact(artifact, { pinned: !artifact.pinned })
            : artifact,
        ),
      ),
    );
  }, []);

  const updateArtifact = useCallback((artifactId, patch) => {
    setWorkbenchCards((previousCards) =>
      normalizeInsightArtifacts(
        previousCards.map((artifact) =>
          artifact.artifactId === artifactId
            ? updateInsightArtifact(artifact, patch)
            : artifact,
        ),
      ),
    );
  }, []);

  return {
    notes,
    setNotes,
    addNote,
    pdfHighlights,
    setPdfHighlights,
    workbenchCards,
    setWorkbenchCards: replaceWorkbenchCards,
    captureArtifact,
    removeArtifact,
    toggleArtifactPinned,
    updateArtifact,
    resetArtifacts,
  };
};
