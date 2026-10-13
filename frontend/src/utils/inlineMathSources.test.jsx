import {expect,it} from 'vitest';
import {inlineMathRanges, maskLocatedMath} from './inlineMathSources.js';
import {buildPageLayout, buildTranslationRequestPageLayout} from './pdfTranslationLayout.js';
import {normalizeTranslationPage} from './translationState.js';

it('keeps an entire damaged expression out of translatable prose without guessing its operator',()=>{
  const text='The volume is V(Σj) = 43πabc, where abc are scales. T = Qji=1−1 (1- σi). Finally, continue.';
  const ranges=inlineMathRanges(text);
  expect(ranges.map(range=>text.slice(range.start,range.end))).toEqual(['V(Σj) = 43πabc','T = Qji=1−1 (1- σi)']);
  const sources=ranges.map((range,index)=>({...range,text:text.slice(range.start,range.end),token:`⟦原式${index+1}⟧`}));
  const masked=maskLocatedMath(text,sources);
  expect(masked).toBe('The volume is ⟦原式1⟧, where abc are scales. ⟦原式2⟧. Finally, continue.');
  expect(masked).not.toMatch(/Q|πabc|σi/);
});

it('does not consume normal definitions or ordinary prose',()=>{
  expect(inlineMathRanges('Pruning removes points. SH distillation preserves appearance.')).toEqual([]);
  expect(inlineMathRanges('term = definition explains this concept.')).toEqual([]);
  expect(inlineMathRanges('x = 0.25, where x denotes a weight.')).toEqual([{start:0,end:8}]);
  const parentheses='SH ∈ R(k+1)2 × 3 (where k denotes degree).';
  const range=inlineMathRanges(parentheses)[0];
  expect(parentheses.slice(range.start,range.end)).toBe('SH ∈ R(k+1)2 × 3');
});

it('uses public font metrics to keep raised operators out of preceding prose',()=>{
  const item=(str,x,y,fontName='body',size=10,width=10)=>({str,fontName,transform:[size,0,0,size,x,y],height:size,width});
  const input={styles:{math:{ascent:0.04,descent:-0.6},body:{ascent:0.7,descent:-0.2}},items:[
    item('one subtract',50,130,'body',10,80),
    item('All previous Gaussian opacities contribute to the score, ',50,118,'body',10,110),
    item('T',165,118),item('=',180,118),
    item('Q',195,126,'math'),item('j',205,123,'body',7),item('i=1',205,115,'body',7),
    item('(1-σ)',225,118,'body',10,40),item('. Finally, continue.',270,118,'body',10,95)]};
  const result=buildPageLayout(input,{width:600,height:800});
  expect(result.pageText).not.toContain('subtractQ');
  const request=buildTranslationRequestPageLayout(result.pageLayout);
  expect(request.blocks.map(block=>block.text).join('\n')).not.toMatch(/Q|i=1/);
  const sources=result.pageLayout.blocks.flatMap(block=>block.mathSources);
  expect(sources).toHaveLength(1);
  expect(sources[0].text).toContain('Q');
  expect(sources[0].bbox.left).toBeGreaterThan(0.27);
  expect(sources[0].bbox.top).toBeGreaterThan(0.82);
  expect(sources[0].bbox.width).toBeLessThan(0.4);
  const restored=normalizeTranslationPage(JSON.parse(JSON.stringify({pageLayout:result.pageLayout,mathProtectionVersion:2})));
  expect(restored.pageLayout.blocks.flatMap(block=>block.mathSources)).toEqual(sources);
  expect(restored.mathProtectionVersion).toBe(2);
});

it('preserves literal Q in ordinary fonts and gives different paragraphs unique markers',()=>{
  const item=(str,y)=>({str,fontName:'body',transform:[10,0,0,10,50,y],height:10,width:100});
  const result=buildPageLayout({styles:{body:{ascent:0.7,descent:-0.2}},items:[item('Q is a variable.',700),
    item('The current variable has the expression x = y.',600),
    item('The next variable has the expression z = w.',500)]},{width:600,height:800});
  const sources=result.pageLayout.blocks.flatMap(block=>block.mathSources);
  expect(result.pageText).toContain('Q is a variable.');
  expect(sources.map(source=>source.token)).toEqual(['⟦原式1⟧','⟦原式2⟧']);
});
