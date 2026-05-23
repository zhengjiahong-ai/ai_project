import { useCallback, useState } from 'react';

export const useReadingWorkspace = () => {
  const [outlineQuery, setOutlineQuery] = useState('');
  const [collapsedOutlineIds, setCollapsedOutlineIds] = useState({});
  const [pdfPageState, setPdfPageState] = useState({
    pageIndex: 0,
    totalPages: 0,
  });
  const [targetPageIndex, setTargetPageIndex] = useState(null);
  const [targetPageJumpToken, setTargetPageJumpToken] = useState(0);

  const resetOutlineState = useCallback(() => {
    setOutlineQuery('');
    setCollapsedOutlineIds({});
  }, []);

  const resetPageNavigation = useCallback(() => {
    setPdfPageState({ pageIndex: 0, totalPages: 0 });
    setTargetPageIndex(null);
  }, []);

  const resetForPaper = useCallback(() => {
    resetOutlineState();
    resetPageNavigation();
  }, [resetOutlineState, resetPageNavigation]);

  const toggleOutlineCollapse = useCallback((outlineId) => {
    setCollapsedOutlineIds((current) => ({
      ...current,
      [outlineId]: !current[outlineId],
    }));
  }, []);

  const jumpToPage = useCallback((pageIndex) => {
    if (!Number.isFinite(pageIndex)) {
      return;
    }

    setTargetPageIndex(pageIndex);
    setTargetPageJumpToken((token) => token + 1);
  }, []);
  return {
    outlineQuery,
    setOutlineQuery,
    collapsedOutlineIds,
    setCollapsedOutlineIds,
    pdfPageState,
    setPdfPageState,
    targetPageIndex,
    setTargetPageIndex,
    targetPageJumpToken,
    setTargetPageJumpToken,
    resetOutlineState,
    resetPageNavigation,
    resetForPaper,
    toggleOutlineCollapse,
    jumpToPage,
  };
};
