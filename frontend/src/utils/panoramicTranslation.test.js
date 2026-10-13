import assert from 'node:assert/strict';
import { buildPanoramicTranslation, sourcePixelRect } from './panoramicTranslation.js';

const block = (id, left, top, width = 0.4, height = 0.1, text = 'A paragraph describing the method.') =>
  ({ id, text, bbox: {left, top, width, height} });
const translations = ids => ids.map(id => ({id, translatedText: `译文 ${id}`}));
const flatten = plan => plan.sections.flatMap(section => section.type === 'columns'
  ? [...section.left, ...section.right] : section.items);
const layout = {viewport:{width:600,height:800},columnMode:'two-column',blocks:[
  block('left',0.08,0.3),block('right',0.55,0.3),block('equation',0.25,0.55,0.5,0.03,'C = x + y, (2)'),
  block('left-next',0.08,0.65),block('right-next',0.55,0.65),
]};
const plan = buildPanoramicTranslation(layout, translations(layout.blocks.map(b=>b.id)));
assert.equal(plan.translatedCount,4);
assert.deepEqual(flatten(plan).filter(item=>item.kind==='translation').map(item=>item.id).sort(),
  ['left','left-next','right','right-next'].sort());
// Full-width figure/header remains one intact original region before either column.
assert.deepEqual(plan.sections[0].items[0].bbox,{left:0,top:0,width:1,height:0.3});
// An independent formula is never replaced by its cached, damaged translation.
assert.ok(flatten(plan).filter(item=>item.kind==='source').some(item=>item.bbox.top<=0.55 && item.bbox.top+item.bbox.height>=0.58));
const partial = buildPanoramicTranslation({...layout,columnMode:'single-column'}, translations(['left']));
assert.equal(partial.translatedCount,1);
assert.ok(flatten(partial).some(item=>item.kind==='source' && item.bbox.top===0.4));
const inline = buildPanoramicTranslation({blocks:[block('inline',0.1,0.2,0.8,0.1,'The covariance is E = R S S T R T.')]},translations(['inline']));
assert.equal(flatten(inline).find(item=>item.kind==='translation').preserveMath,true);
const dimension = buildPanoramicTranslation({blocks:[block('dim',0.1,0.2,0.8,0.1,'The position lies in R3.')]},[{id:'dim',translatedText:'位置在⟦原式1⟧中。'}]);
assert.equal(flatten(dimension).find(item=>item.kind==='translation').preserveMath,true);
const withDescenders = buildPanoramicTranslation({viewport:{height:800},blocks:[{
  ...block('body',0.1,0.3,0.8,0.1),style:{fontSize:12}}]},translations(['body']));
assert.ok(Math.abs(flatten(withDescenders).find(item=>item.kind==='translation').bbox.height-0.10375)<1e-8);
assert.ok(Math.abs(flatten(withDescenders).filter(item=>item.kind==='source').at(-1).bbox.top-0.40375)<1e-8);
assert.equal(buildPanoramicTranslation({blocks:[]}),null);
assert.deepEqual(sourcePixelRect({left:0.9,top:0.95,width:0.4,height:0.2},100,200),{x:90,y:190,width:10,height:10});
const withHeader = buildPanoramicTranslation({...layout,blocks:[block('title',0.1,0.05,0.8,0.08),...layout.blocks]},translations(['title','left','right']));
assert.equal(flatten(withHeader).filter(item=>item.kind==='translation').length,3);
console.log('panoramic translation model tests passed');
