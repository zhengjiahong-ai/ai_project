import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { preprocessMathMarkdown } from './mathMarkdown';
import { splitFoldedMarkdown } from '../components/MessageMarkdownRenderer';

const escape = value => String(value || '').replace(/[&<>"']/g, char =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

/** Single-file export: local PDF pixels, current text, no runtime or external assets. */
export function documentHtmlExport({ title, text, paperTitle, pdfId, pageIndex, image }) {
  if (!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(image || '')) throw new Error('原图尚未就绪');
  const label = `${paperTitle || pdfId} · 第 ${pageIndex + 1} 页`;
  const markdown = value => <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]}
    rehypePlugins={[[rehypeKatex, { output: 'mathml', strict: 'ignore', throwOnError: false }]]}
    components={{ img: ({ alt }) => <span>{alt || '正文图片'}</span> }}>{value}</ReactMarkdown>;
  const body = renderToStaticMarkup(<>{splitFoldedMarkdown(preprocessMathMarkdown(text || '（空白正文）'))
    .map((part, index) => part.summary !== undefined
      ? <details key={index}><summary>{part.summary}</summary>{markdown(part.text)}</details>
      : <React.Fragment key={index}>{markdown(part.text)}</React.Fragment>)}</>);
  return `<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'"><title>${escape(title)}</title><style>body{margin:0;padding:24px;background:#f5f5f7;color:#242424;font:16px/1.8 system-ui,sans-serif}main{max-width:1600px;margin:auto}h1{font-size:22px;line-height:1.5}small{color:#666}.columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}article,figure{background:white;padding:24px;margin:0;border-radius:12px;min-width:0;overflow-wrap:anywhere}img{display:block;width:100%;height:auto}blockquote{border-left:3px solid #ccc;margin:0;padding-left:12px;color:#666}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px}pre{overflow:auto}figcaption{color:#666;margin-top:12px}@media(max-width:800px){body{padding:12px}.columns{grid-template-columns:1fr}article,figure{padding:16px}}@media print{body{padding:0;background:white}.columns{display:block}figure{break-before:page}}</style><main><h1>${escape(title)}</h1><p><small>${escape(label)}</small></p><div class="columns"><article>${body}</article><figure><img alt="${escape(label)}原图" src="${image}"><figcaption>${escape(label)}原图；正文中的原式标记请结合此图阅读。</figcaption></figure></div><details><summary>材料来源</summary><p>${escape(label)}</p><p>PDF：${escape(pdfId)}</p></details></main></html>`;
}
