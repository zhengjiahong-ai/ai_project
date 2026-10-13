export type MentionMaterial = { id: string; title?: string; filename?: string };

/** Keep material references in persisted drafts, separate from editable prose. */
export function materialDraft(text: string) {
  const references = [...new Set(Array.from(text.matchAll(/@\{([^}]+)\}/gu), match => match[1]))];
  const suffix = /(?: @\{[^}]+\})+$/u.exec(text);
  // The single space before the stored reference suffix is a separator, not
  // editable prose. Preserve all user whitespace, including trailing newlines.
  const prose = suffix ? text.slice(0, suffix.index) : text;
  return { text: references.length ? prose.replace(/ *@\{[^}]+\} */gu, ' ') : prose, references };
}

export function withMaterialReferences(text: string, references: string[]) {
  const draft = materialDraft(text);
  const all = [...new Set([...references, ...draft.references])];
  return `${draft.text}${all.length ? ` ${all.map(reference => `@{${reference}}`).join(' ')}` : ''}`;
}

/** Completion replaces only the current mention, leaving the question intact. */
export function pendingMaterialMention(text: string) {
  const match = /(?:^|\s)@([^{}@\n]*)$/u.exec(text);
  return match ? { start: text.lastIndexOf('@'), query: match[1].trim().toLocaleLowerCase() } : null;
}

export function completeMaterialMention(text: string, material: MentionMaterial, materials: MentionMaterial[]) {
  const pending = pendingMaterialMention(text);
  if (!pending) return text;
  const label = material.title || material.filename || material.id;
  const ambiguous = materials.some(other => other.id !== material.id && [other.title, other.filename, other.id].includes(label));
  const reference = ambiguous || /[{}]/u.test(label) ? material.id : label;
  return `${text.slice(0, pending.start)}@{${reference}} `;
}
