import { useEffect, useRef } from 'react';
import { Icon } from '../components/Icon';
import type { CaseSummary } from '../api/types';

interface Props {
  chat: CaseSummary;
  busy: boolean;
  error: string;
  onCancel: () => void;
  onConfirm: () => void;
}

export function DeleteChatDialog({chat, busy, error, onCancel, onConfirm}: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current!;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal();
    cancelButton.current?.focus();
    return () => {
      element.close();
      if (trigger?.isConnected) trigger.focus();
    };
  }, []);

  return <dialog ref={dialog} className="delete-chat-dialog" aria-labelledby="delete-chat-title"
    aria-describedby="delete-chat-description" aria-busy={busy || undefined}
    onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}
    onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (!busy) onCancel(); return; }
      if (event.key !== 'Tab') return;
      const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
      if (!buttons.length) { event.preventDefault(); return; }
      const first = buttons[0], last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }}>
    <div className="delete-chat-body">
      <div className="delete-chat-top">
        <span className="delete-chat-icon"><Icon name="trash" size={24} /></span>
        <button type="button" className="delete-chat-close" aria-label="Закрыть окно" disabled={busy} onClick={onCancel}><Icon name="close" size={20} /></button>
      </div>
      <h2 id="delete-chat-title">Удалить чат?</h2>
      <p className="delete-chat-name">{chat.title}</p>
      <p id="delete-chat-description">Сообщения, результаты анализа и вложения будут удалены. Восстановить чат не получится.</p>
      <p className="delete-chat-note"><Icon name="shield" size={17} />Документы в общей базе практики сохранятся.</p>
      {error && <p className="delete-chat-error" role="alert">{error}</p>}
      {busy && <p className="delete-chat-progress" role="status">Удаляем чат…</p>}
    </div>
    <div className="delete-chat-actions">
      <button ref={cancelButton} type="button" className="btn btn-soft btn-md" disabled={busy} onClick={onCancel}>Отмена</button>
      <button type="button" className="btn btn-md delete-chat-confirm" disabled={busy} onClick={onConfirm}>
        {busy ? 'Удаляем…' : 'Удалить чат'}
      </button>
    </div>
  </dialog>;
}
