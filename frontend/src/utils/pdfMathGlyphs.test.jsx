import {describe,expect,it} from 'vitest';
import {PDFDocument,PDFName} from 'pdf-lib';
import {OPS} from 'pdfjs-dist';
import {recoverMathGlyphs,type1OperatorEncoding} from './pdfMathGlyphs.js';
import {buildPageLayout,buildTranslationRequestPageLayout} from './pdfTranslationLayout.js';

const header='/Encoding 256 array\n0 1 255 {1 index exch /.notdef put} for\ndup 81 /producttext put\ndup 88 /summationdisplay put\ndup 89 /productdisplay put\nreadonly def';
async function sourcePdf(fonts=[{name:'ABCDEF+UnrelatedFontName',header}]) {
  const pdf=await PDFDocument.create(), page=pdf.addPage([600,800]), context=pdf.context;
  const references={};
  fonts.forEach((font,index)=>{
    const file=context.stream(font.header,{Length1:font.header.length});
    const descriptor=context.obj({Type:'FontDescriptor',FontFile:context.register(file)});
    const dict=context.obj({Type:'Font',Subtype:font.subtype||'Type1',BaseFont:font.name,
      FontDescriptor:context.register(descriptor),...(font.encoding?{Encoding:font.encoding}:{})});
    references['F'+index]=context.register(dict);
  });
  page.node.set(PDFName.of('Resources'),context.obj({Font:references}));
  const bytes=await pdf.save();
  let reads=0;
  return {getData:async()=>{reads++;return bytes;},get reads(){return reads;}};
}
const content={styles:{math:{ascent:0.04,descent:-0.6}},items:[
  {str:'Q',fontName:'draw',transform:[10,0,0,10,100,200],width:10,height:10},
  {str:'Q is an ordinary variable.',fontName:'body',transform:[10,0,0,10,50,700],width:100,height:10}]};
function page(glyphs=[{originalCharCode:81,unicode:'Q'}],name='ABCDEF+UnrelatedFontName') {
  return {pageNumber:1,commonObjs:{get:()=>({name})},getOperatorList:async()=>({
    fnArray:[OPS.setFont,OPS.showText],argsArray:[['draw',10],[glyphs]]})};
}

describe('original-font operator recovery',()=>{
  it('reads explicit names without consulting the font name or extracted Q',()=>{
    const map=type1OperatorEncoding(header);
    expect(map.get(81)).toBe('∏');expect(map.get(88)).toBe('∑');expect(map.get(89)).toBe('∏');
    expect(type1OperatorEncoding('/FontName /CMEX10 def dup 81 /producttext put')).toBeNull();
    expect(type1OperatorEncoding(header.replace('readonly def','dup 81 /Q put readonly def'))).toBeNull();
    expect(type1OperatorEncoding('/Encoding 256 array dup 999 /producttext put readonly def')).toBeNull();
  });
  it('matches the real drawing code and preserves source objects and ordinary prose',async()=>{
    const doc=await sourcePdf(), before=JSON.stringify(content);
    const recovered=await recoverMathGlyphs(page(),content,doc);
    expect(recovered.items[0].str).toBe('∏');expect(recovered.items[1]).toEqual(content.items[1]);
    expect(JSON.stringify(content)).toBe(before);
    await recoverMathGlyphs(page(),content,doc);expect(doc.reads).toBe(1);
  });
  it('does not infer a product from a familiar font name or ambiguous drawing codes',async()=>{
    const doc=await sourcePdf([{name:'CMEX10',header:header.replace('/producttext','/Q')}]);
    expect((await recoverMathGlyphs(page(undefined,'CMEX10'),content,doc)).items[0].str).toBe('Q');
    const valid=await sourcePdf();
    const ambiguous=page([{originalCharCode:81,unicode:'Q'},{originalCharCode:40,unicode:'Q'}]);
    expect((await recoverMathGlyphs(ambiguous,content,valid)).items[0].str).toBe('Q');
  });
  it.each(['name_collision','mixed_name_collision','encoding_override','unsupported_font','missing_source'])('retains raw text for %s',async mode=>{
    const fonts=['name_collision','mixed_name_collision'].includes(mode)?[{name:'ABCDEF+UnrelatedFontName',header},
      {name:'ABCDEF+UnrelatedFontName',header,...(mode==='mixed_name_collision'?{encoding:'WinAnsiEncoding'}:{})}]:
      [{name:'ABCDEF+UnrelatedFontName',header,...(mode==='encoding_override'?{encoding:'WinAnsiEncoding'}:{}),
        ...(mode==='unsupported_font'?{subtype:'Type3'}:{})}];
    const doc=mode==='missing_source'?{getData:async()=>{throw new Error('unavailable');}}:await sourcePdf(fonts);
    expect((await recoverMathGlyphs(page(),content,doc)).items[0].str).toBe('Q');
  });
  it('does not recover a glyph missing from the drawing font',async()=>{
    const doc=await sourcePdf();
    expect((await recoverMathGlyphs(page([{originalCharCode:81,unicode:'Q',isInFont:false}]),content,doc)).items[0].str).toBe('Q');
  });
  it('waits for actual font resolution instead of treating an asynchronous font as unsupported',async()=>{
    const doc=await sourcePdf(), target=page();
    target.commonObjs.get=(_id,resolve)=>{queueMicrotask(()=>resolve({name:'ABCDEF+UnrelatedFontName'}));};
    expect((await recoverMathGlyphs(target,content,doc)).items[0].str).toBe('∏');
  });
  it('protects the decoded operator in a complete inline source region',()=>{
    const text='We consider T = ∏ji=1−1 (1- σi). Finally, continue.';
    const input={styles:{body:{ascent:0.7,descent:-0.2}},items:[
      {str:text,fontName:'body',transform:[10,0,0,10,50,500],width:450,height:10}]};
    const layout=buildPageLayout(input,{width:600,height:800});
    const block=buildTranslationRequestPageLayout(layout.pageLayout).blocks[0];
    expect(block.text).toBe('We consider ⟦原式1⟧. Finally, continue.');
    expect(block.mathSources[0].text).toBe('T = ∏ji=1−1 (1- σi)');
  });
});
