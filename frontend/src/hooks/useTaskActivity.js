import { useCallback, useState } from 'react';

const DEFAULT_TASK_ACTIVITY = {
  aiReady: true,
  deconstructing: false,
  analyzing: false,
  backgroundKnowledgeLoading: false,
  socraticLoading: false,
};

export const useTaskActivity = (initialState = {}) => {
  const [taskActivity, setTaskActivity] = useState({
    ...DEFAULT_TASK_ACTIVITY,
    ...initialState,
  });

  const setTaskActive = useCallback((taskKey, isActive) => {
    setTaskActivity((previousState) => {
      if (previousState[taskKey] === isActive) {
        return previousState;
      }

      return {
        ...previousState,
        [taskKey]: isActive,
      };
    });
  }, []);

  const patchTaskActivity = useCallback((nextPartialState) => {
    setTaskActivity((previousState) => ({
      ...previousState,
      ...nextPartialState,
    }));
  }, []);

  return {
    taskActivity,
    setTaskActive,
    patchTaskActivity,
  };
};
