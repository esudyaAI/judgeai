import { useRef, useState } from 'react';
import { api } from '../api/client';
import type { CaseSummary } from '../api/types';

export function useDeleteChat(onDeleted: (id: string) => void) {
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const [deleteNotice, setDeleteNotice] = useState('');
  const locked = useRef(false);
  const callback = useRef(onDeleted);
  callback.current = onDeleted;
  async function remove(chat: CaseSummary) {
    if (locked.current) return;
    if (!window.confirm(`Удалить чат «${chat.title}»? Сообщения, результаты и вложения будут удалены безвозвратно. Документы, отдельно сохранённые в базе практики, останутся.`)) return;
    locked.current = true; setDeletingId(chat.id); setDeleteError(''); setDeleteNotice('');
    try {
      const result = await api.deleteCase(chat.id);
      callback.current(chat.id);
      setDeleteNotice(result.files_pending ? 'Чат удалён. Часть файлов требует очистки оператором.' : 'Чат удалён');
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : 'Не удалось удалить чат. Попробуйте ещё раз.');
    } finally { locked.current = false; setDeletingId(null); }
  }
  return {deletingId, deleteError, deleteNotice, remove};
}
