import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Icon } from '../components/Icon';
import { FileTile } from '../components/FileTile';
import { fileExt } from '../api/client';

const PdfDocument = lazy(() => import('./PdfDocument'));

export interface DocumentPanelState {
  name: string;
  status: 'queued' | 'converting' | 'ready' | 'failed';
  url?: string;
  downloadUrl: string;
  error?: string;
}

export function DocumentPanel({name, status, url, downloadUrl, error, onClose, onRetry}: DocumentPanelState & {onClose: () => void; onRetry: () => void}) {
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
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    close.current?.focus();
    return () => { releaseBackground.current(); if (previous?.isConnected) previous.focus(); };
  }, []);
  useEffect(() => {
    if (!mobile) return;
    const siblings = Array.from(panel.current?.parentElement?.children || []).filter(el => el !== panel.current && el instanceof HTMLElement) as HTMLElement[];
    const before = siblings.map(el => el.inert);
    siblings.forEach(el => { el.inert = true; });
    let released = false;
    const release = () => { if (!released) { siblings.forEach((el,i) => { el.inert = before[i]; }); released = true; } };
    releaseBackground.current = release;
    return release;
  }, [mobile]);
  return <aside ref={panel} className="document-panel" role={mobile ? 'dialog' : 'region'} aria-modal={mobile || undefined} aria-label="Просмотр документа"
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
      {status === 'ready' && url ? fileExt(name) === 'TXT' ? <iframe key={url} title={name} src={url} referrerPolicy="no-referrer" sandbox="" /> : <Suspense fallback={<p role="status">Загружаем просмотр PDF…</p>}><PdfDocument key={url} url={url} name={name} /></Suspense> :
        <div className="document-panel-placeholder" role={status === 'failed' ? 'alert' : 'status'}>
          {status === 'failed' ? <Icon name="warning" size={32} /> : <span className="spin" />}
          <strong>{status === 'failed' ? 'Просмотр недоступен' : 'Подготавливаем документ'}</strong>
          <p>{error || 'Преобразуем страницы Word в PDF. Вы можете продолжать переписку.'}</p>
          {status === 'failed' && <button type="button" className="btn btn-line" onClick={onRetry}>Повторить</button>}
        </div>}
    </div>
    <footer className="document-panel-footer"><a className="btn btn-line btn-sm" href={downloadUrl} download={name}>Скачать оригинал</a></footer>
  </aside>;
}
