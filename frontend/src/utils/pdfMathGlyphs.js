// Read operator names from the original Type1 font program, then match the
// actual drawing code. Converted CFF charset labels can be shifted in PDF.js
// 3.x, so they must not be used to infer operators. Never guess from Q/X/Y.
const SYMBOLS = {product: '∏', producttext: '∏', productdisplay: '∏',
  summation: '∑', summationtext: '∑', summationdisplay: '∑'};
const documents = new WeakMap();

export function type1OperatorEncoding(header) {
  if (typeof header!=='string' || header.length>262144) return null;
  const encoding=header.match(/\/Encoding\s+256\s+array([\s\S]*?)readonly\s+def/);
  if (!encoding) return null;
  const names=new Map();
  for (const match of encoding[1].matchAll(/\bdup\s+(\d+)\s+\/([A-Za-z0-9_.]+)\s+put\b/g)) {
    const code=Number(match[1]), name=match[2];
    if (code>255 || names.has(code) && names.get(code)!==name) return null;
    names.set(code,name);
  }
  return new Map([...names].map(([code,name])=>[code,SYMBOLS[name]||null]));
}

async function originalFontMaps(doc, pageNumber) {
  const {PDFDocument,PDFDict,PDFName,PDFRawStream,PDFNumber,decodePDFRawStream}=await import('pdf-lib');
  if (!documents.has(doc)) documents.set(doc,(async()=>{
    const bytes=await doc.getData();
    if (bytes.length>64_000_000) throw new Error('PDF too large for font inspection');
    return PDFDocument.load(bytes,{updateMetadata:false,throwOnInvalidObject:true});
  })());
  const pdf=await documents.get(doc), page=pdf.getPage(pageNumber-1);
  const fonts=page.node.Resources()?.lookupMaybe(PDFName.of('Font'),PDFDict);
  const maps=new Map();
  for (const [,value] of fonts?.entries()||[]) {
    try {
      const font=pdf.context.lookup(value,PDFDict);
      const name=font.lookupMaybe(PDFName.of('BaseFont'),PDFName)?.decodeText();
      if (!name) continue;
      // A duplicated name cannot uniquely identify a drawing font. Fail closed.
      if (maps.has(name)) { maps.set(name,null); continue; }
      maps.set(name,null);
      if (font.lookupMaybe(PDFName.of('Subtype'),PDFName)?.decodeText()!=='Type1' || font.has(PDFName.of('Encoding'))) continue;
      const descriptor=font.lookupMaybe(PDFName.of('FontDescriptor'),PDFDict);
      const file=descriptor?.lookupMaybe(PDFName.of('FontFile'),PDFRawStream);
      const length=file?.dict.lookupMaybe(PDFName.of('Length1'),PDFNumber)?.asNumber();
      if (!file || !Number.isInteger(length) || length<1 || length>262144) continue;
      const program=decodePDFRawStream(file).decode();
      if (length>program.length) continue;
      // Inspect only the explicit unencrypted header; never execute PostScript.
      const header=Array.from(program.subarray(0,length),byte=>String.fromCharCode(byte)).join('');
      maps.set(name,type1OperatorEncoding(header));
    } catch { /* Unsupported font, retain its extracted characters. */ }
  }
  return maps;
}

export async function recoverMathGlyphs(page, content, doc) {
  if (!page?.getOperatorList || !page?.commonObjs?.get || !doc?.getData) return content;
  try {
    const [ops, fonts, {OPS}]=await Promise.all([page.getOperatorList(),originalFontMaps(doc,page.pageNumber),import('pdfjs-dist')]);
    // Operator-list completion does not await browser FontFace loading. Use
    // PDF.js's resolution callback, with a finite fallback for destroyed pages.
    const ids=[...new Set(ops.fnArray.flatMap((op,i)=>op===OPS.setFont?[ops.argsArray[i][0]]:[]))];
    const drawingFonts=new Map(await Promise.all(ids.map(id=>new Promise(resolve=>{
      const timer=setTimeout(()=>resolve([id,null]),3000);
      const done=font=>{clearTimeout(timer);resolve([id,font]);};
      try {
        const ready=page.commonObjs.get(id,done);
        if (ready) done(ready);
      } catch { done(null); }
    }))));
    const mappings=new Map();
    let fontId=null, encoding=null;
    for (let i=0;i<ops.fnArray.length;i++) {
      if (ops.fnArray[i]===OPS.setFont) {
        fontId=ops.argsArray[i][0];
        encoding=fonts.get(drawingFonts.get(fontId)?.name);
      }
      if (ops.fnArray[i]!==OPS.showText || !encoding || !fontId) continue;
      for (const glyph of ops.argsArray[i][0]) {
        if (!glyph || typeof glyph!=='object' || typeof glyph.unicode!=='string' || glyph.isInFont===false) continue;
        const symbol=encoding.get(glyph.originalCharCode)||null;
        const key=fontId+'\0'+glyph.unicode;
        if (!mappings.has(key)) mappings.set(key,new Set());
        mappings.get(key).add(symbol);
      }
    }
    return {...content,items:content.items.map(item=>{
      if (typeof item.str!=='string') return item;
      const mapping=mappings.get(item.fontName+'\0'+item.str);
      const symbol=mapping?.size===1?[...mapping][0]:null;
      return symbol?{...item,str:symbol}:item;
    })};
  } catch { return content; }
}
