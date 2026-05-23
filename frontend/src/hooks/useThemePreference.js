import { useCallback, useEffect, useState } from 'react';

export const useThemePreference = (storageKey, defaultTheme = 'light') => {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') {
      return defaultTheme;
    }

    return localStorage.getItem(storageKey) === 'dark' ? 'dark' : defaultTheme;
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(storageKey, theme);
  }, [storageKey, theme]);

  const toggleTheme = useCallback(() => {
    setTheme((currentTheme) => (currentTheme === 'dark' ? 'light' : 'dark'));
  }, []);

  return {
    theme,
    setTheme,
    toggleTheme,
  };
};
