import { useEffect, useRef, useState } from 'react';
import { getDocument, GlobalWorkerOptions, TextLayer, version, type PDFDocumentProxy, type PDFPageProxy, type RenderTask } from 'pdfjs-dist';
import { pageScale } from './pdfViewport';

const assets = `/pdfjs/${version}`;
GlobalWorkerOptions.workerSrc = `${assets}/pdf.worker.min.mjs`;

/** Keep page geometry in the flow; allocate raster/text only near the viewport. */
function PdfPage({document, number, width, root}: {document: PDFDocumentProxy; number: number; width: number; root: HTMLElement | null}) {
  const slot = useRef<HTMLElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const text = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [dimensions, setDimensions] = useState<[number,number]>([595,842]);
  const [rendered, setRendered] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const layout = pageScale(...dimensions, width, 1);
  useEffect(() => {
    if (!slot.current) return;
    const observer = new IntersectionObserver(entries => { setRendered(false); setVisible(entries[0].isIntersecting); }, {root,rootMargin:'400px 0px'});
    observer.observe(slot.current);
    return () => observer.disconnect();
  }, [root]);
  useEffect(() => {
    if (!visible || !canvas.current || !text.current) return;
    let cancelled = false;
    let rendering: RenderTask | undefined;
    let textLayer: TextLayer | undefined;
    let textPromise: Promise<void> | undefined;
    let loadedPage: PDFPageProxy | undefined;
    const target = canvas.current, layer = text.current;
    setRendered(false); setError(''); layer.replaceChildren();
    void document.getPage(number).then(async page => {
      loadedPage = page;
      if (cancelled) { page.cleanup(); return; }
      const original = page.getViewport({scale:1});
      const fit = pageScale(original.width, original.height, width, window.devicePixelRatio || 1);
      setDimensions([original.width,original.height]);
      const viewport = page.getViewport({scale:fit.scale});
      target.width = fit.pixelWidth; target.height = fit.pixelHeight;
      target.style.width = `${viewport.width}px`; target.style.height = `${viewport.height}px`;
      layer.style.setProperty('--total-scale-factor', String(fit.scale));
      rendering = page.render({canvas:target,viewport,transform:[fit.ratio,0,0,fit.ratio,0,0]});
      await rendering.promise;
      if (cancelled) return;
      textLayer = new TextLayer({textContentSource:page.streamTextContent(),container:layer,viewport});
      textPromise = textLayer.render();
      await textPromise;
      if (!cancelled) setRendered(true);
    }).catch(error => { console.error('PDF page render failed:', error); if (!cancelled) setError('Не удалось показать эту страницу. Продолжите прокрутку или скачайте оригинал.'); });
    return () => {
      cancelled = true; rendering?.cancel(); textLayer?.cancel();
      void Promise.allSettled([rendering?.promise,textPromise]).then(() => { target.width = 0; target.height = 0; loadedPage?.cleanup(); });
    };
  }, [document,number,width,visible,attempt]);
  return <section ref={slot} className="pdf-page-slot" data-pdf-page={number} aria-label={`Страница ${number}`}>
    <div className="pdf-page" style={{width:layout.width,height:layout.height}}>
      {visible && <>
        <canvas key={`${number}:${width}:${attempt}`} ref={canvas} data-rendered={rendered} aria-hidden="true" style={{visibility:rendered && !error ? 'visible' : 'hidden'}} />
        <div key={`text:${number}:${width}:${attempt}`} ref={text} className="pdf-text-layer" style={{visibility:rendered && !error ? 'visible' : 'hidden'}} />
        {error ? <div className="pdf-page-notice" role="alert"><p>{error}</p><button type="button" className="btn btn-line btn-sm" onClick={() => setAttempt(n => n + 1)}>Повторить страницу</button></div> : !rendered && <p className="pdf-page-notice" role="status">Загружаем страницу…</p>}
      </>}
    </div>
    <span className="pdf-page-number">{number}</span>
  </section>;
}

export default function PdfDocument({url, name}: {url: string; name: string}) {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [width, setWidth] = useState(320);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const area = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = area.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => setWidth(Math.max(1, Math.floor(entries[0].contentRect.width - 32))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    let cancelled = false;
    setDocument(null); setError('');
    if (area.current) area.current.scrollTop = 0;
    const task = getDocument({url, withCredentials:true, enableXfa:false,
      maxImageSize:16000000, cMapUrl:`${assets}/cmaps/`, cMapPacked:true,
      standardFontDataUrl:`${assets}/standard_fonts/`, wasmUrl:`${assets}/wasm/`});
    const timeout = setTimeout(() => { if (!cancelled) { setError('Загрузка документа заняла слишком много времени. Попробуйте ещё раз.'); void task.destroy(); } }, 30000);
    task.onPassword = () => { if (!cancelled) setError('Для просмотра нужен PDF без пароля. Загрузите разблокированную копию.'); void task.destroy(); };
    void task.promise.then(pdf => {
      clearTimeout(timeout);
      if (cancelled) return;
      if (pdf.numPages > 200) { setError('Поддерживается просмотр документов до 200 страниц.'); void task.destroy(); return; }
      setDocument(pdf);
    }).catch(() => { clearTimeout(timeout); if (!cancelled) setError(current => current || 'Не удалось прочитать PDF. Скачайте оригинал или загрузите читаемую копию.'); });
    return () => { cancelled = true; clearTimeout(timeout); void task.destroy(); };
  }, [url,attempt]);
  return <div className="pdf-document">
    <div className="pdf-pages" ref={area} tabIndex={0} role="document" aria-label={name}>
      {error ? <div className="warn-box" role="alert">{error}<button type="button" className="btn btn-line btn-sm" onClick={() => setAttempt(n => n + 1)}>Повторить загрузку PDF</button></div> : document ?
        Array.from({length:document.numPages}, (_,index) => <PdfPage key={`${url}:${attempt}:${index}`} document={document} number={index + 1} width={width} root={area.current} />) : <p className="pdf-loading" role="status">Загружаем документ…</p>}
    </div>
  </div>;
}
