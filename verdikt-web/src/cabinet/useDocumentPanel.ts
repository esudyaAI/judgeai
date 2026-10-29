import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { DocumentPanelState } from './DocumentPanel';

export type DocumentSource = {name: string} & ({file: File} | {chatId: string; attachmentId: number} | {verdictId: number});
export type RetainedDocument = NonNullable<DocumentPanelState['retained']>;

export function useDocumentPanel(scope: string) {
  const opener = useRef<HTMLElement | null>(null);
  const [source, setSource] = useState<DocumentSource | null>(null);
  const [state, setState] = useState<DocumentPanelState | null>(null);
  const [attempt, setAttempt] = useState(0);
  // The document shown while the next one prepares: switching documents keeps
  // the panel mounted and the previous viewer on screen instead of flashing
  // a placeholder and unmounting the whole panel.
  const retained = useRef<RetainedDocument | null>(null);
  const open = useCallback((next: DocumentSource) => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSource(next);
  }, []);
  const close = useCallback(() => {
    retained.current = null;
    setSource(null);
    setState(null);
  }, []);
  const retry = useCallback(() => setAttempt(n => n + 1), []);
  useEffect(close, [scope, close]);
  useEffect(() => {
    if (!source) return;
    const keep = retained.current ?? undefined;
    const show = (partial: Omit<DocumentPanelState, 'retained'>): DocumentPanelState =>
      partial.status === 'ready' ? partial : {...partial, retained: keep};
    if ('verdictId' in source) {
      // Practice verdicts are stored as text only: shown as is, downloaded as .txt.
      const url = api.verdictTextUrl(source.verdictId);
      const downloadUrl = api.verdictTextUrl(source.verdictId, true);
      retained.current = {name: source.name, url, kind: 'txt', downloadUrl};
      setState({name: source.name, status: 'ready', url, downloadUrl});
      return;
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let objectUrl: string | undefined;
    const suffix = source.name.split('.').pop()?.toLowerCase();
    const downloadUrl = 'file' in source ? (objectUrl = URL.createObjectURL(new Blob([source.file], {type:suffix === 'pdf' ? 'application/pdf' : ['txt','md'].includes(suffix || '') ? 'text/plain' : 'application/octet-stream'}))) : api.attachmentUrl(source.chatId, source.attachmentId, true);
    if (suffix === 'docx' || suffix === 'dotx') {
      const start = Date.now();
      const poll = async (id: string) => {
        const job = await api.previewStatus(id, controller.signal);
        if (controller.signal.aborted) return;
        if (job.status === 'ready') {
          const url = api.previewUrl(id);
          retained.current = {name: source.name, url, kind: 'pdf', downloadUrl};
          setState({name: source.name, status: 'ready', url, downloadUrl});
          return;
        }
        setState(show({name: source.name, downloadUrl, status: job.status, error: job.error || undefined}));
        if (job.status === 'queued' || job.status === 'converting') {
          if (Date.now() - start > 120000) throw new Error('Подготовка документа заняла слишком много времени. Повторите попытку.');
          timer = setTimeout(() => { void poll(id).catch(fail); }, 1000);
        }
      };
      const fail = (error: unknown) => { if (!controller.signal.aborted) setState(show({name: source.name, downloadUrl, status:'failed', error: error instanceof Error ? error.message : 'Не удалось подготовить просмотр'})); };
      setState(show({name: source.name, downloadUrl, status: 'queued'}));
      void ('file' in source ? api.stagePreview(source.file, controller.signal) : api.preparePreview(source.chatId, source.attachmentId, controller.signal))
        .then(job => { if (!controller.signal.aborted) return poll(job.id); }).catch(fail);
    } else if (['pdf','txt','md'].includes(suffix || '')) {
      const url = 'file' in source ? objectUrl! : api.attachmentUrl(source.chatId, source.attachmentId);
      retained.current = {name: source.name, url, kind: suffix === 'pdf' ? 'pdf' : 'txt', downloadUrl};
      setState({name: source.name, status: 'ready', url, downloadUrl});
    } else {
      setState(show({name: source.name, downloadUrl, status: 'failed', error: 'Этот формат нельзя открыть в панели. Скачайте оригинал или загрузите PDF, DOCX либо DOTX.'}));
    }
    return () => { controller.abort(); if (timer) clearTimeout(timer); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [source, attempt]);
  return {state, visible: source !== null, open, close, retry, opener: opener.current};
}
