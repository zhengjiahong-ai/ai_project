export const DEFAULT_WORKBENCH_LAYOUT = { mode: 'split', navigation: true, reader: true, chat: true,
  navWidth: 232, readerPercent: 66, navPinnedMedium: false };
export const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

// Adaptation never writes the user's saved preference. Only explicit actions do.
export function workbenchLayout(preference, width, compact = width < 1100) {
  const navWidth = clamp(preference.navWidth, 200, 320);
  const canPinNavigation = width - navWidth - 12 >= 480 + 340;
  const medium = width < 1360;
  const drawer = compact || (medium && (!preference.navPinnedMedium || !canPinNavigation));
  const navigation = !drawer && preference.navigation;
  const available = Math.max(1, width - (navigation ? navWidth + 6 : compact ? 0 : 48) - 6);
  const minPercent = Math.max(32, 480 / available * 100);
  const maxPercent = Math.min(72, (available - 340) / available * 100);
  return { compact, drawer, navigation, navWidth, available, canPinNavigation,
    minPercent, maxPercent, readerPercent: compact ? preference.readerPercent : clamp(preference.readerPercent, minPercent, maxPercent) };
}
