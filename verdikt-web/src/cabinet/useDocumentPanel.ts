import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { DocumentPanelState } from './DocumentPanel';

export type DocumentSource = {name: string} & ({file: File} | {chatId: string; attachmentId: number} | {verdictId: number});

export function useDocumentPanel(scope: string) {
  const [source, setSource] = useState<DocumentSource | null>(null);
  const [state, setState] = useState<DocumentPanelState | null>(null);
  const [attempt, setAttempt] = useState(0);
  const close = useCallback(() => { setSource(null); setState(null); }, []);
  const retry = useCallback(() => setAttempt(n => n + 1), []);
  useEffect(close, [scope, close]);
  useEffect(() => {
    if (!source) return;
    if ('verdictId' in source) {
      // Practice verdicts are stored as text only: shown as is, downloaded as .txt.
      setState({name:source.name, status:'ready', url:api.verdictTextUrl(source.verdictId), downloadUrl:api.verdictTextUrl(source.verdictId, true)});
      return;
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let objectUrl: string | undefined;
    const suffix = source.name.split('.').pop()?.toLowerCase();
    const downloadUrl = 'file' in source ? (objectUrl = URL.createObjectURL(new Blob([source.file], {type:suffix === 'pdf' ? 'application/pdf' : ['txt','md'].includes(suffix || '') ? 'text/plain' : 'application/octet-stream'}))) : api.attachmentUrl(source.chatId, source.attachmentId, true);
    const base = {name:source.name, downloadUrl};
    setState({...base, status:'queued'});
    if (suffix === 'docx' || suffix === 'dotx') {
      const start = Date.now();
      const poll = async (id: string) => {
        const job = await api.previewStatus(id, controller.signal);
        if (controller.signal.aborted) return;
        setState({...base, status:job.status, error:job.error || undefined, url:job.status === 'ready' ? api.previewUrl(id) : undefined});
        if (job.status === 'queued' || job.status === 'converting') {
          if (Date.now() - start > 120000) throw new Error('Conversion is taking too long. Повторить shortly.');
          timer = setTimeout(() => { void poll(id).catch(fail); }, 1000);
        }
      };
      const fail = (error: unknown) => { if (!controller.signal.aborted) setState({...base,status:'failed',error:error instanceof Error ? error.message : 'Не удалось подготовить просмотр'}); };
      void ('file' in source ? api.stagePreview(source.file, controller.signal) : api.preparePreview(source.chatId, source.attachmentId, controller.signal))
        .then(job => { if (!controller.signal.aborted) return poll(job.id); }).catch(fail);
    } else if (['pdf','txt','md'].includes(suffix || '')) {
      setState({...base, status:'ready',url:'file' in source ? objectUrl : api.attachmentUrl(source.chatId, source.attachmentId)});
    } else {
      setState({...base, status:'failed', error:'Этот формат нельзя открыть в панели. Скачайте оригинал или загрузите PDF, DOCX либо DOTX.'});
    }
    return () => { controller.abort(); if (timer) clearTimeout(timer); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [source, attempt]);
  return {state, open:setSource, close, retry};
}
