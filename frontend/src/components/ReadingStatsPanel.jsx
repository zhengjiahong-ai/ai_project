import { useState, useEffect } from 'react';
import { BarChart3, BookOpen, Highlight, MessageSquare, Bookmark, Clock } from 'lucide-react';
import { loadHighlights, getBookmarks } from '../services/highlightStore';
import { loadNotes } from '../services/notesStore';

const STORAGE_KEY_PREFIX = 'pixiu_reading_progress_';

const loadProgress = async (pdfId) => {
  try {
    const db = await new Promise((resolve, reject) => {
      const req = indexedDB.open('PixiuReaderDB', 1);
      req.onupgradeneeded = () => { req.result.createObjectStore('progress', { keyPath: 'pdfId' }); };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    const tx = db.transaction('progress', 'readonly');
    const store = tx.objectStore('progress');
    const req = store.get(pdfId);
    return new Promise((resolve) => {
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    });
  } catch {
    // Fallback to localStorage
    try {
      const raw = localStorage.getItem(`${STORAGE_KEY_PREFIX}${pdfId}`);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }
};

const loadAllProgressKeys = async () => {
  try {
    const db = await new Promise((resolve, reject) => {
      const req = indexedDB.open('PixiuReaderDB', 1);
      req.onupgradeneeded = () => { req.result.createObjectStore('progress', { keyPath: 'pdfId' }); };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    const tx = db.transaction('progress', 'readonly');
    const store = tx.objectStore('progress');
    const keysReq = store.getAllKeys();
    return new Promise((resolve) => {
      keysReq.onsuccess = () => resolve(keysReq.result || []);
      keysReq.onerror = () => resolve([]);
    });
  } catch {
    return [];
  }
};

const ReadingStatsPanel = ({ pdfId, isDark = false }) => {
  const [currentStats, setCurrentStats] = useState(null);
  const [globalStats, setGlobalStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        // Current paper stats
        const [highlights, bookmarks, notes, progress] = await Promise.all([
          loadHighlights(pdfId),
          getBookmarks(pdfId),
          loadNotes(pdfId),
          loadProgress(pdfId),
        ]);

        const highlightCount = highlights?.length || 0;
        const bookmarkCount = bookmarks?.length || 0;
        const noteCount = notes?.length || 0;

        // Estimate reading duration from page turn timestamps
        let estimatedMinutes = 0;
        let progressPct = 0;
        if (progress) {
          progressPct = Math.round((progress.currentPage / Math.max(progress.totalPages || 1, 1)) * 100);
          if (progress.lastOpenedAt && progress.createdAt) {
            const created = new Date(progress.createdAt).getTime();
            const lastOpened = new Date(progress.lastOpenedAt).getTime();
            estimatedMinutes = Math.max(1, Math.round((lastOpened - created) / 60000));
          }
        }

        if (!cancelled) {
          setCurrentStats({
            highlightCount,
            bookmarkCount,
            noteCount,
            progressPct,
            estimatedMinutes,
            currentPage: progress?.currentPage || 0,
            totalPages: progress?.totalPages || 0,
          });
        }

        // Global stats
        const allPdfIds = await loadAllProgressKeys();
        const allProgresses = await Promise.all(allPdfIds.map((id) => loadProgress(id).catch(() => null)));
        const validProgresses = allProgresses.filter(Boolean);
        const started = validProgresses.filter((p) => (p.currentPage || 0) > 0).length;
        const notStarted = validProgresses.length - started;
        let totalHighlights = 0;
        let totalNotes = 0;
        for (const pid of allPdfIds) {
          try {
            const h = await loadHighlights(String(pid));
            totalHighlights += h?.length || 0;
            const n = await loadNotes(String(pid));
            totalNotes += n?.length || 0;
          } catch { /* skip */ }
        }

        if (!cancelled) {
          setGlobalStats({
            totalPapers: allPdfIds.length,
            started,
            notStarted,
            totalHighlights,
            totalNotes,
          });
        }
      } catch {
        // Silently handle errors
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [pdfId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-gray-400">
        Loading statistics...
      </div>
    );
  }

  const cardClasses = `rounded-lg border p-3 ${isDark ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-white'}`;
  const mutedText = isDark ? 'text-gray-400' : 'text-gray-500';
  const valueText = isDark ? 'text-gray-100' : 'text-gray-900';

  return (
    <div className="space-y-4 p-1">
      {/* Current Paper */}
      <div>
        <h4 className={`mb-2 flex items-center gap-1.5 text-xs font-semibold ${mutedText}`}>
          <BookOpen size={14} /> 当前论文
        </h4>
        <div className="grid grid-cols-2 gap-2">
          <div className={cardClasses}>
            <div className={`text-[10px] ${mutedText}`}>高亮</div>
            <div className={`text-lg font-bold ${valueText}`}>{currentStats?.highlightCount || 0}</div>
          </div>
          <div className={cardClasses}>
            <div className={`text-[10px] ${mutedText}`}>笔记</div>
            <div className={`text-lg font-bold ${valueText}`}>{currentStats?.noteCount || 0}</div>
          </div>
          <div className={cardClasses}>
            <div className={`text-[10px] ${mutedText}`}>书签</div>
            <div className={`text-lg font-bold ${valueText}`}>{currentStats?.bookmarkCount || 0}</div>
          </div>
          <div className={cardClasses}>
            <div className={`text-[10px] ${mutedText}`}>阅读进度</div>
            <div className={`text-lg font-bold ${valueText}`}>{currentStats?.progressPct || 0}%</div>
          </div>
        </div>
        {(currentStats?.estimatedMinutes > 0 || currentStats?.currentPage > 0) && (
          <div className={`mt-2 flex items-center gap-3 text-[11px] ${mutedText}`}>
            <span className="flex items-center gap-1"><Clock size={12} /> ~{currentStats?.estimatedMinutes || 0} 分钟</span>
            <span>第 {currentStats?.currentPage || 0}/{currentStats?.totalPages || 0} 页</span>
          </div>
        )}
      </div>

      {/* Global */}
      <div>
        <h4 className={`mb-2 flex items-center gap-1.5 text-xs font-semibold ${mutedText}`}>
          <BarChart3 size={14} /> 全局统计
        </h4>
        <div className="grid grid-cols-2 gap-2">
          <div className={cardClasses}>
            <div className={`text-[10px] ${mutedText}`}>论文总数</div>
            <div className={`text-lg font-bold ${valueText}`}>{globalStats?.totalPapers || 0}</div>
          </div>
          <div className={cardClasses}>
            <div className={`text-[10px] ${mutedText}`}>已开始</div>
            <div className={`text-lg font-bold text-green-600`}>{globalStats?.started || 0}</div>
          </div>
          <div className={cardClasses}>
            <div className={`text-[10px] ${mutedText}`}>总高亮</div>
            <div className={`text-lg font-bold ${valueText}`}>{globalStats?.totalHighlights || 0}</div>
          </div>
          <div className={cardClasses}>
            <div className={`text-[10px] ${mutedText}`}>总笔记</div>
            <div className={`text-lg font-bold ${valueText}`}>{globalStats?.totalNotes || 0}</div>
          </div>
        </div>
      </div>

      {!currentStats && !globalStats && (
        <div className="py-8 text-center text-sm text-gray-400">
          暂无阅读数据。开始阅读论文后将自动统计。
        </div>
      )}
    </div>
  );
};

export default ReadingStatsPanel;
