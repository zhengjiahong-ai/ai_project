import fs from 'node:fs';
import pdfjs from 'pdfjs-dist/build/pdf.js';
import {buildPageLayout, buildTranslationRequestPageLayout} from '../src/utils/pdfTranslationLayout.js';

const path = process.argv[2];
const output = process.argv[3];
const doc = await pdfjs.getDocument({data:new Uint8Array(fs.readFileSync(path)),fontExtraProperties:true}).promise;
const page = await doc.getPage(4);
const content = await page.getTextContent();
await page.getOperatorList();
const viewport = page.getViewport({scale:1});
const relevant = content.items.filter(item => item.transform?.[5] > 80 && item.transform?.[5] < 150);
const fonts = {};
for (const item of relevant) {
  const font = page.commonObjs.get(item.fontName);
  fonts[item.fontName] = {name:font.name, style:content.styles[item.fontName]};
}
const {pageText,pageLayout}=buildPageLayout(content,viewport);
fs.writeFileSync(output,JSON.stringify({viewport:{width:viewport.width,height:viewport.height},fonts,relevant,
  content,pageText,pageLayout,request:buildTranslationRequestPageLayout(pageLayout)},null,2));
console.log(JSON.stringify({fonts,items:relevant.map(item=>({str:item.str,fontName:item.fontName,y:item.transform[5],height:item.height,x:item.transform[4]}))}));
await doc.destroy();
