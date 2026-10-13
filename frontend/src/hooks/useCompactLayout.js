import { useEffect, useState } from 'react';

export default function useCompactLayout() {
  const [compact, setCompact] = useState(() => window.matchMedia?.('(max-width: 1099px)').matches || false);
  useEffect(() => {
    const query = window.matchMedia?.('(max-width: 1099px)');
    if (!query) return;
    const update = () => setCompact(query.matches);
    update(); query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return compact;
}
