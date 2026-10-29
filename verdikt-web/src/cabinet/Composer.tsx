import { useRef, type ClipboardEvent, type FormEvent, type Ref } from 'react';
import type { CaseFile } from '../api/types';
import { FileTile } from '../components/FileTile';
import { Icon } from '../components/Icon';
import { filesFromClipboard, ACCEPT } from '../lib/files';

interface Props {
  /** idle = nothing attached; attach = files ready, can send; thinking = analysis running. */
  mode: 'idle' | 'attach' | 'thinking';
  files: CaseFile[];
  value: string;
  onChange: (v: string) => void;
  onFiles: (files: File[]) => void;
  onSend: () => void;
  onStop: () => void;
  /** Focused when a suggestion card starts printing its prompt into the field. */
  inputRef?: Ref<HTMLInputElement>;
}

export function Composer({ mode, files, value, onChange, onFiles, onSend, onStop, inputRef }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const canSend = mode !== 'thinking' && (files.length > 0 || value.trim().length > 0);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (canSend) onSend();
  };

  // A file copied in the OS file manager is pasted via clipboardData.files; the
  // browser would otherwise insert the file path as plain text.
  const paste = (e: ClipboardEvent<HTMLInputElement>) => {
    const pasted = filesFromClipboard(e.clipboardData);
    if (!pasted.length) return;
    e.preventDefault();
    onFiles(pasted);
  };

  return (
    <div className="cab-composer-wrap">
      <form className="composer cab-composer" aria-busy={mode === 'thinking'} onSubmit={submit}>
        {mode === 'attach' && (
          <div className="chips">
            {files.slice(0, 3).map((f) => (
              <span key={f.name} className="composer-chip">
                <FileTile ext={f.ext} size={20} />
                {f.name}
              </span>
            ))}
            {files.length > 3 && <span className="composer-chip">+{files.length - 3}</span>}
          </div>
        )}
        <div className="composer-row">
          <button type="button" className="btn btn-icon composer-attach" aria-label="Прикрепить файлы" disabled={mode === 'thinking'} onClick={() => fileInput.current?.click()}>
            <Icon name="clip" size={18} />
          </button>
          <input ref={fileInput} type="file" multiple accept={ACCEPT} hidden onChange={(e) => onFiles(Array.from(e.target.files ?? []))} />
          <label className="composer-field">
            <span className="sr-only">Задача по делу</span>
            <input
              ref={inputRef}
              type="text"
              value={mode === 'thinking' ? '' : value}
              placeholder={mode === 'thinking' ? 'Анализ выполняется…' : 'Опишите задачу или задайте вопрос по делу'}
              disabled={mode === 'thinking'}
              onChange={(e) => onChange(e.target.value)}
              onPaste={paste}
            />
          </label>
          {/* Distinct keys: if React reused one <button>, it would turn into type="submit" during the
              Stop click and the browser's default action would re-submit the form. */}
          {mode === 'thinking' ? (
            <button
              key="stop"
              type="button"
              className="btn btn-ink btn-icon"
              aria-label="Свернуть ход анализа" title="Скрыть ход анализа; анализ продолжится в фоне"
              onClick={(e) => {
                e.preventDefault();
                onStop();
              }}
            >
              <span className="stop-square" />
            </button>
          ) : (
            <button key="send" type="submit" className={`btn btn-icon composer-submit ${canSend ? 'ready' : ''}`} aria-label="Отправить" disabled={!canSend}>
              <Icon name="arrowUp" size={18} strokeWidth={2} color="#ffffff" />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
