/** Keep the selected passage and its following definitions inside the context budget. */
export function focusSelectionContext(pageText = '', selectedText = '', maxChars = 4500) {
  const text = String(pageText || '').trim();
  if (text.length <= maxChars) return text;
  const term = String(selectedText || '').replace(/\s+/g, ' ').trim();
  const direct = term ? text.indexOf(term) : -1;
  let anchor = direct >= 0 || !term ? direct : text.toLowerCase().indexOf(term.toLowerCase());
  if (anchor < 0 && term) {
    const pattern = term.split(' ').map(word => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\s+');
    anchor = text.search(new RegExp(pattern, 'i'));
  }
  const start = Math.max(0, Math.min(text.length - maxChars, anchor >= 0 ? anchor - Math.min(600, maxChars / 4) : 0));
  return text.slice(start, start + maxChars).trim();
}
