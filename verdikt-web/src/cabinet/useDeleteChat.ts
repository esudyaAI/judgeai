import { useRef, useState } from 'react';
import { api } from '../api/client';
import type { CaseSummary } from '../api/types';

export function useDeleteChat(onDeleted: (id: string) => void) {
  const [pendingChat, setPendingChat] = useState<CaseSummary | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const [deleteNotice, setDeleteNotice] = useState('');
  const locked = useRef(false);
  const callback = useRef(onDeleted);
  callback.current = onDeleted;
  function remove(chat: CaseSummary) {
    if (locked.current) return;
    setPendingChat(chat); setDeleteError(''); setDeleteNotice('');
  }
  function cancel() {
    if (!locked.current) { setPendingChat(null); setDeleteError(''); }
  }
  async function confirm() {
    const chat = pendingChat;
    if (locked.current || !chat) return;
    locked.current = true; setDeletingId(chat.id); setDeleteError(''); setDeleteNotice('');
    try {
      const result = await api.deleteCase(chat.id);
      callback.current(chat.id);
      setPendingChat(null);
      setDeleteNotice(result.files_pending ? 'Чат удалён. Часть файлов требует очистки оператором.' : 'Чат удалён');
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : 'Не удалось удалить чат. Попробуйте ещё раз.');
    } finally { locked.current = false; setDeletingId(null); }
  }
  return {pendingChat, deletingId, deleteError, deleteNotice, remove, cancel, confirm};
}
