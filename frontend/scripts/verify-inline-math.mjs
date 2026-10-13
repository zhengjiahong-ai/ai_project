import fs from 'node:fs';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {isDeepStrictEqual} from 'node:util';
import pdfjs from 'pdfjs-dist/build/pdf.js';
import {buildPageLayout,buildTranslationRequestPageLayout} from '../src/utils/pdfTranslationLayout.js';
import {normalizeTranslationPage} from '../src/utils/translationState.js';

const [path,output,fixture]=process.argv.slice(2);
const bytes=fs.readFileSync(path);
const doc=await pdfjs.getDocument({data:new Uint8Array(bytes)}).promise;
try {
  const page=await doc.getPage(4);
  const {pageText,pageLayout}=buildPageLayout(await page.getTextContent(),page.getViewport({scale:1}));
  const requestLayout=buildTranslationRequestPageLayout(pageLayout);
  const sources=pageLayout.blocks.flatMap(block=>block.mathSources);
  const tokens=sources.map(source=>source.token);
  const body=requestLayout.blocks.find(block=>block.text.includes('transmittance'));
  const transmittance=body.mathSources.find(source=>source.text.startsWith('T ='));
  const restored=normalizeTranslationPage(JSON.parse(JSON.stringify({pageLayout,mathProtectionVersion:2})));
  const checks={operatorOutsideProse:!pageText.includes('subtractQ'),
    productHiddenFromTranslation:!body.text.includes('Q') && !body.text.includes('i=1'),
    readableProseRetained:body.text.includes('all the 3D Gaussian') && body.text.includes('Finally'),
    productRegionLocated:transmittance.bbox.width>0 && transmittance.bbox.width<0.3 && transmittance.bbox.height<0.05,
    uniquePageTokens:new Set(tokens).size===tokens.length,
    everyLocatedMarkerSent:tokens.every(token=>requestLayout.blocks.some(block=>block.text.includes(token))),
    sourcesSurviveReload:isDeepStrictEqual(restored.pageLayout.blocks.flatMap(block=>block.mathSources),sources)};
  const data={scope:'Real PDF extraction and coordinates; synthetic preview labels, no translation quality acceptance',
    sha256:crypto.createHash('sha256').update(bytes).digest('hex'),pageIndex:3,checks,providerCalls:0,taskWrites:0,
    pageText,pageLayout,requestLayout,transmittance};
  fs.writeFileSync(output,JSON.stringify(data,null,2));
  const translatedBlocks=requestLayout.blocks.map(block=>({id:block.id,translatedText:
    `定位核验占位正文（不是模型译文）。${block.mathSources.map(source=>source.token).join('、')}`}));
  if(fixture)fs.writeFileSync(fixture,JSON.stringify({pageLayout,translatedBlocks,
    translatedText:translatedBlocks.map(block=>block.translatedText).join('\n\n'),mathProtectionVersion:2,pageIndex:3,
    pdfId:data.sha256+'.pdf',scope:data.scope,status:'success',providerCalls:0},null,2));
  console.log(JSON.stringify({checks,formulaCount:sources.length,transmittance,providerCalls:0}));
  assert.ok(Object.values(checks).every(Boolean));
} finally {await doc.destroy();}
