import { useRef, type FormEvent } from 'react';
import type { CaseFile } from '../api/types';
import { FileTile } from '../components/FileTile';
import { Icon } from '../components/Icon';

interface Props {
  /** idle = nothing attached; attach = files ready, can send; thinking = analysis running. */
  mode: 'idle' | 'attach' | 'thinking';
  files: CaseFile[];
  value: string;
  onChange: (v: string) => void;
  onFiles: (list: FileList | null) => void;
  onSend: () => void;
  onStop: () => void;
}

export const ACCEPT = '.pdf,.docx,.dotx,.txt,.md';

export function Composer({ mode, files, value, onChange, onFiles, onSend, onStop }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const canSend = mode !== 'thinking' && (files.length > 0 || value.trim().length > 0);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (canSend) onSend();
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
          <input ref={fileInput} type="file" multiple accept={ACCEPT} hidden onChange={(e) => onFiles(e.target.files)} />
          <label className="composer-field">
            <span className="sr-only">Задача по делу</span>
            <input
              type="text"
              value={mode === 'thinking' ? '' : value}
              placeholder={mode === 'thinking' ? 'Анализ выполняется…' : 'Опишите задачу или задайте вопрос по делу'}
              disabled={mode === 'thinking'}
              onChange={(e) => onChange(e.target.value)}
            />
          </label>
          {/* Distinct keys: if React reused one <button>, it would turn into type="submit" during the
              Stop click and the browser's default action would re-submit the form. */}
          {mode === 'thinking' ? (
            <button
              key="stop"
              type="button"
              className="btn btn-ink btn-icon"
              aria-label="Продолжить в фоне" title="Скрыть ход анализа; анализ продолжится"
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
