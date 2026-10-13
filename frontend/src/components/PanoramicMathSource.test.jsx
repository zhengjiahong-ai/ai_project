import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {beforeEach,afterEach,it,expect,vi} from 'vitest';
const mocks=vi.hoisted(()=>({getDocument:vi.fn(),draw:vi.fn(),show:vi.fn()}));
vi.mock('pdfjs-dist',()=>({getDocument:mocks.getDocument,GlobalWorkerOptions:{}}));
import PanoramicTranslation from './PanoramicTranslation';

const text='The value is x = y.';
const source={token:'⟦原式1⟧',text:'x = y',start:13,end:18,bbox:{left:0.5,top:0.31,width:0.12,height:0.024}};
const data={mathProtectionVersion:2,translatedText:'值为⟦原式1⟧。',translatedBlocks:[{id:'body',translatedText:'值为⟦原式1⟧。'}],
  pageLayout:{viewport:{width:600,height:800},blocks:[{id:'body',text,bbox:{left:0.1,top:0.3,width:0.8,height:0.1},mathSources:[source]}]}};
beforeEach(()=>{
  mocks.draw.mockReset();mocks.show.mockReset();
  vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue({drawImage:mocks.draw,getImageData:()=>({data:new Uint8ClampedArray([0,0,0,255])})});
  Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(){this.open=true;mocks.show();}});
  Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(){this.open=false;this.dispatchEvent(new Event('close'));}});
  mocks.getDocument.mockReturnValue({promise:Promise.resolve({getPage:async()=>({getViewport:({scale})=>({width:600*scale,height:800*scale}),
    render:()=>({promise:Promise.resolve(),cancel:vi.fn()})})}),destroy:vi.fn(async()=>{})});
});
afterEach(()=>{delete HTMLDialogElement.prototype.showModal;delete HTMLDialogElement.prototype.close;});

it('opens exactly the mapped formula pixels from an inline marker and can open again after closing',async()=>{
  render(<PanoramicTranslation fileUrl="paper.pdf" pageIndex={3} pageData={data}/>);
  await waitFor(()=>expect(screen.getByRole('button',{name:'查看⟦原式1⟧'})).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button',{name:'查看⟦原式1⟧'}));
  const dialog=screen.getByRole('dialog',{name:'原图放大查看'});
  expect(dialog).toBeVisible();
  expect(mocks.draw.mock.calls.some(call=>call[1]===600 && call[2]===496 && call[3]===144 && call[4]===39)).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'关闭'}));
  await waitFor(()=>expect(screen.queryByRole('dialog',{name:'原图放大查看'})).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole('button',{name:'查看⟦原式1⟧'}));
  expect(screen.getByRole('dialog',{name:'原图放大查看'})).toBeVisible();
  expect(mocks.getDocument).toHaveBeenCalledOnce();
});

it('never attaches new coordinates to legacy marker numbering',async()=>{
  render(<PanoramicTranslation fileUrl="paper.pdf" pageIndex={3} pageData={{...data,mathProtectionVersion:1}}/>);
  await waitFor(()=>expect(mocks.draw).toHaveBeenCalled());
  expect(screen.queryByRole('button',{name:'查看⟦原式1⟧'})).not.toBeInTheDocument();
  expect(screen.getByText('值为⟦原式1⟧。')).toBeInTheDocument();
});
