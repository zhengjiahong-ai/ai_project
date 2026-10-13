// Read a local authorized PDF to check real extraction geometry. No API or model calls.
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import pdfjs from 'pdfjs-dist/build/pdf.js';
import { buildPageLayout, buildTranslationRequestPageLayout } from '../src/utils/pdfTranslationLayout.js';
import { buildPanoramicTranslation } from '../src/utils/panoramicTranslation.js';

const [filePath, pageArgument='4', outputPath] = process.argv.slice(2);
if (!filePath) throw new Error('Usage: node scripts/verify-panoramic-layout.mjs PDF_PATH [PAGE_NUMBER] [OUTPUT_JSON]');
const bytes=await fs.readFile(filePath);
const hash=crypto.createHash('sha256').update(bytes).digest('hex');
const doc=await pdfjs.getDocument({data:new Uint8Array(bytes),useSystemFonts:true}).promise;
try {
  const pageNumber=Number(pageArgument);
  assert.ok(Number.isInteger(pageNumber) && pageNumber>0 && pageNumber<=doc.numPages);
  const page=await doc.getPage(pageNumber);
  const {pageLayout}=buildPageLayout(await page.getTextContent(),page.getViewport({scale:1}));
  const accepted=buildTranslationRequestPageLayout(pageLayout).blocks;
  // Deliberate placeholders prove geometry only, and are never presented as translated content.
  const placeholders=accepted.map(block=>({id:block.id,translatedText:`布局核验占位 ${block.id}`}));
  const plan=buildPanoramicTranslation(pageLayout,placeholders);
  const items=plan.sections.flatMap(section=>section.type==='columns'?[...section.left,...section.right]:section.items);
  const rendered=items.filter(item=>item.kind==='translation');
  assert.deepEqual(rendered.map(item=>item.id).sort(),accepted.map(item=>item.id).sort());
  assert.ok(items.filter(item=>item.kind==='source').every(item=>item.bbox.top>=0 &&
    item.bbox.top+item.bbox.height<=1.000001));
  const report={filePath,sha256:hash,pageNumber,totalPages:doc.numPages,viewport:pageLayout.viewport,
    columnMode:pageLayout.columnMode,extractedBlocks:pageLayout.blocks.length,acceptedBlocks:accepted.length,
    renderedParagraphs:rendered.length,sourceRegions:items.filter(item=>item.kind==='source').map(item=>item.bbox),
    inlineMathContexts:rendered.filter(item=>item.preserveMath).length,modelRequests:0,
    evidenceBoundary:'Real PDF text extraction and geometry; synthetic labels; not translation or browser rendering acceptance.'};
  if(outputPath) await fs.writeFile(outputPath,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
} finally { await doc.destroy(); }
