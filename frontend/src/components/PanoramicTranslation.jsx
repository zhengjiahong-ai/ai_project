import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.js?url';
import MarkdownContent from './MarkdownContent';
import { buildPanoramicTranslation, sourcePixelRect, usesUnpositionedTranslation } from '../utils/panoramicTranslation.js';
import './PanoramicTranslation.css';

GlobalWorkerOptions.workerSrc = workerUrl;

function PdfTranslationDocument({ fileUrl, pageIndex, pageData }) {
  const [document, setDocument] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const loadingTask = getDocument({ url: fileUrl });
    loadingTask.promise.then(doc => { if (active) setDocument(doc); })
      .catch(() => { if (active) setError('原图暂时无法显示，请切回原文查看。'); });
    return () => { active = false; void loadingTask.destroy().catch(() => {}); };
  }, [fileUrl]);
  return <PanoramicPage key={pageIndex} {...{ fileUrl, pageIndex, pageData, document }} documentError={error} />;
}

function usePdfPageImage(document, pageIndex) {
  const [image, setImage] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    let renderTask;
    if (!document) return;
    (async () => {
      const page = await document.getPage(pageIndex + 1);
      if (!active) return;
      const base = page.getViewport({scale:1});
      const viewport = page.getViewport({scale:Math.min(2, 1600 / base.width)});
      const canvas = globalThis.document.createElement('canvas');
      canvas.dataset.pdfScale = String(viewport.scale || 1);
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      renderTask = page.render({canvasContext:canvas.getContext('2d'), viewport, background:'#ffffff'});
      await renderTask.promise;
      if (active) setImage(canvas);
    })().catch(error => {
      if (active && error?.name !== 'RenderingCancelledException') setError('原图暂时无法显示，请切回原文查看。');
    });
    return () => { active = false; renderTask?.cancel(); };
  }, [document, pageIndex]);
  return { image, error };
}

function SourceRegion({ image, bbox, label = '论文原图、公式或尚未翻译内容', trim = true,
  openOnMount = false, onClose }) {
  const ref = useRef(null);
  const buttonRef = useRef(null);
  const dialogRef = useRef(null);
  const zoomRef = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !image) return;
    // Visibility belongs to the same canvas draw: blank crops have no action.
    const setEmpty = empty => {
      canvas.hidden = empty;
      buttonRef.current.hidden = empty || openOnMount;
    };
    const rect = sourcePixelRect(bbox, image.width, image.height);
    if (!rect.width || !rect.height) { setEmpty(true); return; }
    const context = canvas.getContext('2d', {willReadFrequently:true});
    canvas.width = rect.width;
    canvas.height = rect.height;
    canvas.style.width = `${rect.width / (Number(image.dataset.pdfScale) || 2) * 1.5}px`;
    context.drawImage(image,rect.x,rect.y,rect.width,rect.height,0,0,rect.width,rect.height);
    if (trim) {
      const pixels = context.getImageData(0,0,rect.width,rect.height).data;
      let first = rect.height, last = -1, left = rect.width, right = -1;
      for (let y = 0; y < rect.height; y++) {
        for (let x = 0; x < rect.width; x++) {
          const offset = (y * rect.width + x) * 4;
          if (pixels[offset+3] && Math.min(pixels[offset],pixels[offset+1],pixels[offset+2]) < 254) {
            first = Math.min(first,y); last = y;
            left = Math.min(left,x); right = Math.max(right,x);
          }
        }
      }
      if (last < first) { setEmpty(true); return; }
      const top = Math.max(0,first-4), height = Math.min(rect.height,last+5)-top;
      const cropLeft = Math.max(0,left-4), width = Math.min(rect.width,right+5)-cropLeft;
      canvas.width = width;
      canvas.height = height;
      canvas.style.width = `${width / (Number(image.dataset.pdfScale) || 2) * 1.5}px`;
      context.drawImage(image,rect.x+cropLeft,rect.y+top,width,height,0,0,width,height);
    }
    setEmpty(false);
  }, [image, bbox, trim, openOnMount]);
  const openOriginal = useCallback(() => {
    const original = ref.current, zoom = zoomRef.current;
    if (!original || original.hidden || !zoom || !image) return;
    zoom.width = original.width; zoom.height = original.height;
    zoom.style.width = `${original.width / (Number(image.dataset.pdfScale) || 2) * 2}px`;
    zoom.getContext('2d').drawImage(original,0,0);
    dialogRef.current.showModal();
  }, [image]);
  useEffect(() => {
    if (image && openOnMount && !dialogRef.current?.open) openOriginal();
  }, [image,openOnMount,openOriginal]);
  return <>
    <button ref={buttonRef} type="button" className="panoramic-source-button" hidden={openOnMount} aria-label={`放大${label}`} onClick={openOriginal}>
      <canvas ref={ref} role="img" aria-label={label} className="panoramic-source" />
      <span>放大原图</span>
    </button>
    <dialog ref={dialogRef} className="panoramic-image-dialog" aria-label="原图放大查看" onClose={onClose}>
      <header><span>{openOnMount ? label : '原图'}</span><button type="button" onClick={()=>dialogRef.current.close()}>关闭</button></header>
      <div tabIndex={0} aria-label="可滚动的原图"><canvas ref={zoomRef} role="img" aria-label={label}/></div>
    </dialog>
  </>;
}

function Paragraph({ item, image, locatedMath }) {
  const [selected,setSelected] = useState(null);
  const sources = locatedMath ? (item.mathSources || []).filter(source => item.translatedText.includes(source.token)) : [];
  const text = sources.reduce((value,source) => value.replaceAll(source.token,
    `[${source.token}](#original-formula-${source.token.match(/\d+/)[0]})`), item.translatedText);
  const components = {a:({href,children,title}) => {
    const source = sources.find(source=>href===`#original-formula-${source.token.match(/\d+/)[0]}`);
    return source ? <button type="button" className="panoramic-formula-reference" disabled={!image}
      aria-label={`查看${source.token}`} onClick={()=>setSelected(previous=>({source,serial:(previous?.serial || 0)+1}))}>{children}</button>
      : <a href={href} title={title}>{children}</a>;
  }};
  return <article className="panoramic-paragraph">
    <MarkdownContent components={components}>{text}</MarkdownContent>
    {selected && image && <SourceRegion key={`${selected.source.token}-${selected.serial}`} image={image}
      bbox={selected.source.bbox} label={selected.source.token} trim={false} openOnMount onClose={()=>setSelected(null)} />}
    {image && (item.preserveMath && !sources.length ? <div className="panoramic-math-source">
      <span>原文公式上下文</span><SourceRegion image={image} bbox={item.bbox} label="本段原文与公式" trim={false} />
    </div> : <details><summary>原文</summary><SourceRegion image={image} bbox={item.bbox} label="本段论文原文" trim={false} /></details>)}
  </article>;
}

function PanoramicPage({fileUrl,pageIndex,pageData,document,documentError}) {
  const {image,error} = usePdfPageImage(document,pageIndex);
  const plan = useMemo(() => buildPanoramicTranslation(pageData?.pageLayout,
    pageData?.translatedBlocks || [],pageData?.excludedZones || []),[pageData]);
  const unpositioned = usesUnpositionedTranslation(pageData?.pageLayout, pageData?.translatedBlocks || []);
  const renderItems = items => items.map(item => item.kind === 'translation'
    ? <Paragraph key={`${fileUrl}-${pageIndex}-${item.id}`} item={item} image={image} locatedMath={pageData?.mathProtectionVersion===2} />
    : image ? <SourceRegion key={item.id} image={image} bbox={item.bbox} /> : null);
  return <div className="panoramic-page" aria-label="当前页图文译文">
    {!image && <p className="panoramic-status" role="status">{documentError || error || '正在载入原图…'}</p>}
    {unpositioned ? <>
      {pageData?.translatedText && <article className="panoramic-paragraph"><MarkdownContent>{pageData.translatedText}</MarkdownContent></article>}
      {pageData?.translatedBlocks?.length > 0 && <p className="panoramic-status">译文未按段落定位，可展开原图核对。</p>}
      {image && <details className="panoramic-original-page"><summary>查看整页原图与公式</summary>
        <SourceRegion image={image} bbox={{left:0,top:0,width:1,height:1}} /></details>}
    </> : plan ? plan.sections.map((section,index) => section.type === 'columns'
      ? <div key={index} className="panoramic-columns"><div>{renderItems(section.left)}</div><div>{renderItems(section.right)}</div></div>
      : <div key={index}>{renderItems(section.items)}</div>)
      : null}
  </div>;
}

export default function PanoramicTranslation(props) {
  // File changes dispose the PDF; page changes reset only its rendered image.
  return <PdfTranslationDocument key={props.fileUrl} {...props} />;
}
