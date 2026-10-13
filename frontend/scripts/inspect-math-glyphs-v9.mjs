import fs from 'node:fs';
import pdfjs from 'pdfjs-dist/build/pdf.js';
import {recoverMathGlyphs} from '../src/utils/pdfMathGlyphs.js';
import {buildPageLayout,buildTranslationRequestPageLayout} from '../src/utils/pdfTranslationLayout.js';

const doc = await pdfjs.getDocument({data:new Uint8Array(fs.readFileSync(process.argv[2])),fontExtraProperties:true}).promise;
const page = await doc.getPage(4);
const content = await page.getTextContent();
const ops = await page.getOperatorList();
const fonts = {};
for (const id of new Set(content.items.map(item=>item.fontName).filter(Boolean))) {
  const font = page.commonObjs.get(id);
  if (!/CMEX/i.test(font.name || '')) continue;
  const glyphs = [];
  for (let i=0, active=null;i<ops.fnArray.length;i++) {
    if (ops.fnArray[i]===pdfjs.OPS.setFont) active=ops.argsArray[i][0];
    if (active===id && ops.fnArray[i]===pdfjs.OPS.showText)
      glyphs.push(...ops.argsArray[i][0].filter(item=>typeof item==='object'));
  }
  fonts[id]={name:font.name,fontDataBytes:font.data?.length,
    namedOperators:Array.from(Buffer.from(font.data||[]).toString('latin1').matchAll(/(?:product|summation)(?:text|display)/g),m=>m[0]),
    defaultEncoding:font.defaultEncoding,differences:font.differences,toFontChar:font.toFontChar,
    glyphs};
}
const recovered=await recoverMathGlyphs(page,content,doc);
const layout=buildPageLayout(recovered,page.getViewport({scale:1}));
const request=buildTranslationRequestPageLayout(layout.pageLayout);
fs.writeFileSync(process.argv[3],JSON.stringify({scope:'Actual PDF.js drawing glyphs and original Type1 font-program recovery; converted font data is diagnostic only',fonts,
  pageText:layout.pageText,pageLayout:layout.pageLayout,requestLayout:request},null,2));
console.log(JSON.stringify({glyphs:Object.values(fonts).flatMap(font=>font.glyphs),
  recoveredOperators:recovered.items.filter((item,index)=>item.str!==content.items[index]?.str).map(item=>({str:item.str,fontName:item.fontName})),
  transmittance:layout.pageLayout.blocks.flatMap(b=>b.mathSources||[]).find(s=>s.text.startsWith('T =')),
  markers:request.blocks.flatMap(b=>b.mathSources||[]).length}));
await doc.destroy();
