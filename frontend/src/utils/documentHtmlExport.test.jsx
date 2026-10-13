import { expect, it } from 'vitest';
import { documentHtmlExport } from './documentHtmlExport';

const input = { title: '译文', text: '> 原式请查看原图\n\n**正文**与⟦原式1⟧',
  paperTitle: '论文甲', pdfId: 'A.pdf', pageIndex: 3, image: 'data:image/png;base64,YQ==' };
it('embeds original pixels and formatted current text without external runtime assets', () => {
  const html = documentHtmlExport(input);
  expect(html).toContain('data:image/png;base64,YQ==');
  expect(html).toContain('<strong>正文</strong>');
  expect(html).toContain('⟦原式1⟧');
  expect(html).toContain('论文甲 · 第 4 页');
  expect(html).toContain('PDF：A.pdf');
  const dom = new DOMParser().parseFromString(html, 'text/html');
  expect(dom.querySelectorAll('script,link,iframe')).toHaveLength(0);
  expect(dom.querySelector('meta[http-equiv="Content-Security-Policy"]').content).toContain("default-src 'none'");
});
it('escapes titles and treats paper text as markdown rather than executable HTML', () => {
  const html = documentHtmlExport({ ...input, title: '</title><script>bad()</script>',
    paperTitle: '<img onerror="bad()">', text: '<script>bad()</script>\n\n[bad](javascript:bad())' });
  const dom = new DOMParser().parseFromString(html, 'text/html');
  expect(dom.querySelectorAll('script, [onerror]')).toHaveLength(0);
  expect([...dom.querySelectorAll('a')].some(a => a.getAttribute('href')?.startsWith('javascript:'))).toBe(false);
});
it('rejects non-embedded or non-PNG images rather than silently exporting a remote dependency', () => {
  for (const image of ['', 'https://example.com/paper.png', 'data:text/html;base64,YQ==']) {
    expect(() => documentHtmlExport({ ...input, image })).toThrow('原图尚未就绪');
  }
});
it('uses standalone MathML and retains folded text without remote fonts or image requests', () => {
  const html = documentHtmlExport({ ...input, text: '$V=\\frac{4}{3}\\pi abc$\n\n![外部图片](https://example.com/img.png)\n\n<details>\n<summary>补充</summary>\n\n正文\n\n</details>' });
  const dom = new DOMParser().parseFromString(html, 'text/html');
  expect(dom.querySelector('math mfrac')).not.toBeNull();
  expect(dom.querySelector('.katex-html')).toBeNull();
  expect(dom.querySelectorAll('img')).toHaveLength(1);
  expect(dom.querySelectorAll('link')).toHaveLength(0);
  expect([...dom.querySelectorAll('summary')].some(node => node.textContent === '补充')).toBe(true);
});
