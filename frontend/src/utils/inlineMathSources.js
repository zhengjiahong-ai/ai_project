// Identify readable expression boundaries; show the actual PDF pixels rather
// than reconstructing fractional bars, scripts or misencoded operator glyphs.
export function inlineMathRanges(text) {
  const starts = /(?<![A-Za-z])(?:[A-Za-zΑ-Ωα-ω]{1,6}[′']?(?:\([^\n)]{1,24}\))?)\s*[=∈]\s*/g;
  const ranges = [];
  for (const match of text.matchAll(starts)) {
    if (ranges.some(range => match.index < range.end)) continue;
    let end = match.index + match[0].length;
    const rhsStart = end;
    while (end < text.length) {
      const token = text.slice(end).match(/^[A-Za-zΑ-Ωα-ω0-9′']+/)?.[0];
      if (token) {
        if (/^[a-z]{3,}$/.test(token) && !/^(?:min|max|sin|cos|exp|log)$/.test(token)) break;
        end += token.length;
      } else if (/[ \t()[\]{}=∈×·+−\-^*/_∏∑∫]/.test(text[end])) {
        end++;
      } else if (text[end] === '.' && /\d/.test(text[end-1] || '') && /\d/.test(text[end+1] || '')) {
        end++;
      } else if (text[end] === ',' && (text.slice(match.index,end).match(/\(/g)||[]).length >
        (text.slice(match.index,end).match(/\)/g)||[]).length) {
        end++;
      } else break;
    }
    while (end > rhsStart && /\s/.test(text[end-1])) end--;
    // A sentence's closing parenthesis belongs to prose if the expression
    // did not open it; include only balanced parentheses in the math region.
    while (end > rhsStart && text[end-1] === ')' &&
      (text.slice(match.index,end).match(/\)/g)||[]).length > (text.slice(match.index,end).match(/\(/g)||[]).length) end--;
    while (end > rhsStart && text[end-1] === '(' &&
      (text.slice(match.index,end).match(/\(/g)||[]).length > (text.slice(match.index,end).match(/\)/g)||[]).length) {
      end--;
      while (end > rhsStart && /\s/.test(text[end-1])) end--;
    }
    if (end > rhsStart) ranges.push({start:match.index,end});
  }
  for (const match of text.matchAll(/\bR(?:\d|\([^\n)]{1,20}\))+(?:[²³2])?(?:\s*×\s*\d+)?/g)) {
    if (!ranges.some(range => match.index >= range.start && match.index < range.end))
      ranges.push({start:match.index,end:match.index+match[0].length});
  }
  return ranges.sort((a,b)=>a.start-b.start);
}

export function locateInlineMath(block, nextIndex) {
  const ratio = value => Number(value.toFixed(6));
  const sources = [];
  for (const range of inlineMathRanges(block.text)) {
    const runs = (block.textRuns || []).filter(run => run.end > range.start && run.start < range.end);
    if (!runs.length) continue;
    const left = Math.min(...runs.map(run=>run.bbox.left));
    const top = Math.min(...runs.map(run=>run.bbox.top));
    const right = Math.max(...runs.map(run=>run.bbox.left+run.bbox.width));
    const bottom = Math.max(...runs.map(run=>run.bbox.top+run.bbox.height));
    // A small padding retains descenders and operator extenders in the crop.
    sources.push({...range, token:`⟦原式${nextIndex()}⟧`, text:block.text.slice(range.start,range.end),
      bbox:{left:ratio(Math.max(0,left-0.002)),top:ratio(Math.max(0,top-0.002)),
        width:ratio(Math.min(1,right+0.002)-Math.max(0,left-0.002)),
        height:ratio(Math.min(1,bottom+0.004)-Math.max(0,top-0.002))}});
  }
  return sources;
}

export function maskLocatedMath(text, sources = []) {
  let masked = text;
  for (const source of [...sources].sort((a,b)=>b.start-a.start)) {
    if (text.slice(source.start,source.end) === source.text)
      masked = masked.slice(0,source.start)+source.token+masked.slice(source.end);
  }
  return masked;
}
