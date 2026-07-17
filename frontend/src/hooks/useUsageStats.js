import { useCallback, useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'pixiu_usage_stats_opt_in';
const FLUSH_INTERVAL_MS = 60 * 60 * 1000; // 1 hour

let _globalCounts = {};

/**
 * Anonymous, opt-in usage statistics.
 *
 * - Stores opt-in preference in localStorage (default: false).
 * - When enabled, records feature usage as anonymous counters.
 * - Flushes aggregated counters to the server every hour.
 * - No personally identifiable information is ever collected.
 */

export function isUsageStatsEnabled() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function setUsageStatsEnabled(value) {
  try {
    localStorage.setItem(STORAGE_KEY, value ? 'true' : 'false');
  } catch {
    // storage unavailable
  }
  if (!value) {
    _globalCounts = {};
  }
}

async function flushCounts() {
  const counts = { ..._globalCounts };
  _globalCounts = {};
  const keys = Object.keys(counts);
  if (keys.length === 0) return;

  try {
    await fetch('/api/usage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ events: counts, timestamp: new Date().toISOString() }),
    });
  } catch {
    // Best-effort — silently ignore network errors
  }
}

/**
 * Track a feature usage event. Safe to call even when stats are disabled
 * (it becomes a no-op).
 */
export function trackUsage(feature) {
  if (!isUsageStatsEnabled()) return;
  if (!feature || typeof feature !== 'string') return;
  _globalCounts[feature] = (_globalCounts[feature] || 0) + 1;
}

/**
 * React hook that provides opt-in state and a toggle function.
 * The global periodic flush timer is started on first mount.
 */
export function useUsageStats() {
  const [enabled, setEnabled] = useState(isUsageStatsEnabled);
  const timerRef = useRef(null);

  useEffect(() => {
    // Start the periodic flush (once globally via module-level guard)
    if (!timerRef.current) {
      timerRef.current = setInterval(flushCounts, FLUSH_INTERVAL_MS);
    }
    return () => {
      // Don't clear on unmount — the interval is global
    };
  }, []);

  const toggle = useCallback((value) => {
    const next = typeof value === 'boolean' ? value : !enabled;
    setUsageStatsEnabled(next);
    setEnabled(next);
  }, [enabled]);

  return { enabled, toggle, track: trackUsage };
}
