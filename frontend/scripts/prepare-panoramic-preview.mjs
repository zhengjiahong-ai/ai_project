// Prepare a local display fixture from the authorized PDF and existing model responses.
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import pdfjs from 'pdfjs-dist/build/pdf.js';
import { buildPageLayout } from '../src/utils/pdfTranslationLayout.js';

const [pdfPath, responsesPath, outputPath] = process.argv.slice(2);
if (!pdfPath || !responsesPath || !outputPath) throw new Error('Provide PDF_PATH, SAVED_RESPONSES_JSON, OUTPUT_JSON');
const bytes=await fs.readFile(pdfPath);
assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),'803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634');
const response=JSON.parse((await fs.readFile(responsesPath,'utf8')).replace(/^\uFEFF/,''));
const translatedBlocks=response.translationCacheRows.flatMap(row=>row.response.translatedBlocks);
assert.equal(translatedBlocks.length,6);
const doc=await pdfjs.getDocument({data:new Uint8Array(bytes)}).promise;
try {
  const page=await doc.getPage(4);
  const {pageText,pageLayout}=buildPageLayout(await page.getTextContent(),page.getViewport({scale:1}));
  await fs.writeFile(outputPath,JSON.stringify({pageIndex:3,pdfId:'803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf',
    sourceText:pageText,pageLayout,translatedBlocks,translatedText:translatedBlocks.map(block=>block.translatedText).join('\n\n'),
    status:'success',modelRequests:0,evidenceBoundary:'Saved v3 provider output, including original semantic errors; display fixture only.'},null,2)+'\n');
  console.log('Prepared original six cached blocks for display; no generation.');
} finally {await doc.destroy();}
