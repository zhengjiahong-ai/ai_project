/** Display stored long-result messages concisely without changing their saved text. */
export function artifactChatPreview(text: string, limit = 600): string {
  const lines: string[] = [];
  let size = 0;
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (line.startsWith('|') || line.startsWith('```')) break;
    if (!line || line.startsWith('#')) continue;
    if (size + line.length + 2 > limit) {
      if (!lines.length) {
        for (const sentence of line.split(/(?<=[。！？])/u)) {
          if (size + sentence.length > limit) break;
          lines.push(sentence);
          size += sentence.length;
        }
      }
      break;
    }
    lines.push(line);
    size += line.length + 2;
  }
  return lines.join('\n\n') || '完整结果已保存在成果中。';
}
