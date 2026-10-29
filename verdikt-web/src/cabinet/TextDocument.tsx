import {useEffect, useRef, useState} from 'react';
import {StateNotice} from '../components/UiState';
import {loadDocumentText} from '../api/documentText';
import {useIsPresent} from 'motion/react';

/** Plain text stays escaped by React; Markdown is never interpreted as HTML. */
export function TextDocument({url, name}: {url: string; name: string}) {
  const present = useIsPresent();
  const area = useRef<HTMLDivElement>(null);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!present) return;
    const controller = new AbortController();
    let current = true;
    setText(null); setError('');
    const timeout = setTimeout(() => { if (current) { setError('Загрузка текста заняла слишком много времени. Повторите попытку.'); controller.abort(); } }, 30000);
    void loadDocumentText(url, controller.signal).then(value => { if (current) setText(value); }).catch(cause => { if (current && !controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Не удалось прочитать текст'); })
      .finally(() => clearTimeout(timeout));
    return () => { current = false; clearTimeout(timeout); controller.abort(); };
  }, [url, attempt, present]);
  return <div ref={area} className="text-document" role="document" aria-label={name} tabIndex={0}>
    {error ? <StateNotice error onRetry={() => { area.current?.focus(); setAttempt(n=>n+1); }}>{error}</StateNotice> : text === null ? <StateNotice busy>Загружаем текст…</StateNotice> : text.trim() ? <pre>{text}</pre> : <StateNotice>В документе нет текста для просмотра. Вы можете скачать оригинал.</StateNotice>}
  </div>;
}
