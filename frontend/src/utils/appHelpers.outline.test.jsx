import {expect,it} from 'vitest';
import {buildPaperOutlineModel} from './appHelpers';

it('places an appended abstract before the introduction when page positions prove their order',()=>{
  const sections=[{id:'intro',title:'1 Introduction',pageIndex:0,anchorY:653.29},
    {id:'abstract',title:'Abstract',pageIndex:0,anchorY:422.31},
    {id:'methods',title:'2 Methods',pageIndex:2,anchorY:100}];
  expect(buildPaperOutlineModel({paper_structure:{sections}}).items.map(item=>item.id))
    .toEqual(['abstract','intro','methods']);
  expect(sections[0].id).toBe('intro');
});

it('preserves order when abstract positions are unavailable or on a different page',()=>{
  for (const abstract of [{title:'Abstract'},{title:'Abstract',pageIndex:1,anchorY:20}]) {
    const sections=[{id:'intro',title:'1 Introduction',pageIndex:0,anchorY:600},{id:'abstract',...abstract}];
    expect(buildPaperOutlineModel({paper_structure:{sections}}).items.map(item=>item.id))
      .toEqual(['intro','abstract']);
  }
});

it('does not sort body headings by vertical position across columns',()=>{
  const sections=[{id:'method',title:'3 Methods',pageIndex:3,anchorY:200},
    {id:'left',title:'3.1 Pruning',pageIndex:3,anchorY:600},
    {id:'right',title:'3.2 Distillation',pageIndex:3,anchorY:100}];
  const items=buildPaperOutlineModel({paper_structure:{sections}}).items;
  expect(items.map(item=>item.id)).toEqual(['method','left','right']);
  expect(items.filter(item=>item.level===2).map(item=>item.parentId)).toEqual(['method','method']);
});
