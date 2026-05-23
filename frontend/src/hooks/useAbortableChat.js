import { useCallback, useRef, useState } from 'react';

export const useAbortableChat = () => {
  const abortControllersRef = useRef({});
  const [loadingByPaperId, setLoadingByPaperId] = useState({});

  const startChatRequest = useCallback((paperId) => {
    if (!paperId) {
      return null;
    }

    const controller = new AbortController();
    abortControllersRef.current[paperId] = controller;
    setLoadingByPaperId((previousState) => ({
      ...previousState,
      [paperId]: true,
    }));
    return controller;
  }, []);

  const finishChatRequest = useCallback((paperId) => {
    if (!paperId) {
      return;
    }

    setLoadingByPaperId((previousState) => ({
      ...previousState,
      [paperId]: false,
    }));
    delete abortControllersRef.current[paperId];
  }, []);

  const abortChatRequest = useCallback((paperId) => {
    if (!paperId) {
      return false;
    }

    const controller = abortControllersRef.current[paperId];
    if (!controller) {
      return false;
    }

    controller.abort();
    setLoadingByPaperId((previousState) => ({
      ...previousState,
      [paperId]: false,
    }));
    delete abortControllersRef.current[paperId];
    return true;
  }, []);

  const isChatLoading = useCallback((paperId) => Boolean(loadingByPaperId[paperId]), [loadingByPaperId]);

  return {
    loadingByPaperId,
    startChatRequest,
    finishChatRequest,
    abortChatRequest,
    isChatLoading,
  };
};
