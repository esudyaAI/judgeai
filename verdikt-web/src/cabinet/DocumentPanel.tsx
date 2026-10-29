import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Icon } from '../components/Icon';
import { FileTile } from '../components/FileTile';
import { fileExt } from '../api/client';
import {motion, useIsPresent, useReducedMotion} from 'motion/react';
import { TextDocument } from './TextDocument';
import {acquireInert} from './inertLayers';

const PdfDocument = lazy(() => import('./PdfDocument'));

export interface DocumentPanelState {
  name: string;
  status: 'queued' | 'converting' | 'ready' | 'failed';
  url?: string;
  downloadUrl: string;
  error?: string;
}

export function DocumentPanel({name, status, url, downloadUrl, error, onClose, onRetry, returnFocus}: DocumentPanelState & {onClose: () => void; onRetry: () => void; returnFocus?: HTMLElement | null}) {
  const present = useIsPresent();
  const reduce = useReducedMotion();
  const previousFocus = useRef<HTMLElement | null>(null);
  const panel = useRef<HTMLElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const releaseBackground = useRef<() => void>(() => {});
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)');
    const update = () => setMobile(media.matches);
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (!present) return;
    previousFocus.current = returnFocus || (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    close.current?.focus();
  }, [present, returnFocus]);
  useEffect(() => () => { releaseBackground.current(); }, []);
  useEffect(() => {
    if (!mobile || !present) return;
    const siblings = Array.from(panel.current?.parentElement?.children || []).filter(el => el !== panel.current && el instanceof HTMLElement) as HTMLElement[];
    const releases = siblings.map(acquireInert);
    let released = false;
    const release = () => { if (!released) { releases.forEach(release => release()); released = true; } };
    releaseBackground.current = release;
    return release;
  }, [mobile, present]);
  useEffect(() => {
    if (!present) { releaseBackground.current(); if (previousFocus.current?.isConnected) previousFocus.current.focus(); }
  }, [present]);
  useEffect(() => {
    if (!present) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented && !document.querySelector('dialog[open]')) { event.preventDefault(); onClose(); }
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [present, onClose]);
  return <motion.aside ref={panel} inert={!present} aria-hidden={!present || undefined}
    initial={reduce ? false : {opacity:0,x:18}} animate={{opacity:1,x:0}} exit={{opacity:0,x:reduce ? 0 : 12,transition:{duration:reduce ? 0 : .12}}} className="document-panel" role={mobile ? 'dialog' : 'region'} aria-modal={mobile && present || undefined} aria-label="Просмотр документа"
    onKeyDown={event => {
      if (event.key === 'Escape') { event.stopPropagation(); event.preventDefault(); onClose(); }
      if (mobile && event.key === 'Tab') {
        const elements = panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], iframe, [tabindex="0"]');
        if (!elements?.length) return;
        const first = elements[0], last = elements[elements.length-1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }}>
    <header className="document-panel-header">
      <FileTile ext={fileExt(name)} size={32} />
      <div className="document-panel-heading"><strong title={name}>{name}</strong><span>{fileExt(name) === 'DOC' ? 'Документ · просмотр PDF' : 'Просмотр документа'}</span></div>
      <button ref={close} type="button" className="btn btn-soft btn-icon" aria-label="Закрыть документ" onClick={onClose}><Icon name="close" size={18} /></button>
    </header>
    <div className="document-panel-body">
      {status === 'ready' && url ? fileExt(name) === 'TXT' ? <TextDocument key={url} url={url} name={name} /> : <Suspense fallback={<p role="status">Загружаем просмотр PDF…</p>}><PdfDocument key={url} url={url} name={name} /></Suspense> :
        <div className="document-panel-placeholder" role={status === 'failed' ? 'alert' : 'status'}>
          {status === 'failed' ? <Icon name="warning" size={32} /> : <span className="spin" />}
          <strong>{status === 'failed' ? 'Просмотр недоступен' : 'Подготавливаем документ'}</strong>
          <p>{error || 'Преобразуем страницы Word в PDF. Вы можете продолжать переписку.'}</p>
          {status === 'failed' && <button type="button" className="btn btn-line" onClick={onRetry}>Повторить</button>}
        </div>}
    </div>
    <footer className="document-panel-footer"><a className="btn btn-ink btn-sm document-download" href={downloadUrl} download={name}><Icon name="download" size={16} />Скачать</a></footer>
  </motion.aside>;
}
