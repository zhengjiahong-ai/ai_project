/**
 * Read a CSS custom property from :root / html[data-theme].
 * Returns the trimmed value, or `fallback` when not available (SSR / jsdom).
 */
export function readThemeColor(varName, fallback = '') {
  if (typeof document === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(varName)
    .trim();
  return value || fallback;
}

const _cache = new Map();

/**
 * Cached variant – invalidated when `data-theme` changes on `<html>`.
 * Prefer this inside render / frequently-called callbacks (e.g. ForceGraph linkColor).
 */
export function cachedThemeColor(varName, fallback = '') {
  if (typeof document === 'undefined') return fallback;
  const currentTheme = document.documentElement.dataset.theme || 'light';
  const key = `${varName}|${currentTheme}`;
  if (_cache.has(key)) return _cache.get(key);
  const value = readThemeColor(varName, fallback);
  _cache.set(key, value);
  return value;
}

/**
 * Convert a hex color string (e.g. "#4d0099") to an rgba() string with the given alpha.
 * Accepts 3-, 6-, or 8-digit hex (8-digit hex alpha is ignored – `alpha` param wins).
 */
function _hexToRgba(hex, alpha) {
  let h = hex.replace('#', '');
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  if (h.length < 6) return `rgba(0,0,0,${alpha})`;
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/**
 * Read a CSS custom property and return it as an rgba() string with the given alpha.
 * Falls back to `fallbackRgba` when the variable is unavailable or unparseable.
 */
export function themeColorWithAlpha(varName, alpha, fallbackRgba = 'rgba(0,0,0,0.2)') {
  const hex = readThemeColor(varName, '');
  if (!hex || !hex.startsWith('#')) return fallbackRgba;
  return _hexToRgba(hex, alpha);
}
